"""FIFO launch queue in front of remote tmux training jobs.

Without a gate, a wave of submissions starts tmux sessions immediately; every
wrapper script reads the same nvidia-smi snapshot at launch and they pile onto
one card until it OOMs. This module makes the runner thread wait for a slot
before launching:

- FIFO per remote server (host/port/username/output_root identity).
- A job occupies a slot while it is launching or training (status "running",
  or granted-but-not-yet-launched).
- Capacity = max_concurrent_jobs (0 = auto: one per GPU card seen by the
  probe) AND at least one GPU with free memory >= min_free_gpu_mb.
- Fail-open: if the GPU probe errors (no nvidia-smi, SSH hiccup), launches
  proceed count-only — a broken probe must never freeze submissions.
- Waiting is poll-based (2s) so cancel_requested is honored without
  cross-thread signaling.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from web.server.web_security import LOGGER

_QUEUE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "queue.json"
_CONFIG_CACHE_SECONDS = 5.0
_WAIT_POLL_SECONDS = 2.0

_CONFIG_DEFAULTS = {
  "enabled": True,
  "max_concurrent_jobs": 0,  # 0 = auto: one per GPU card reported by the probe
  "min_free_gpu_mb": 8000,
  "probe_interval_seconds": 20,
}

_CONFIG_ENV_OVERRIDES = {
  "enabled": ("WGSC_QUEUE_ENABLED", lambda raw: str(raw).strip().lower() in {"1", "true", "yes", "on"}),
  "max_concurrent_jobs": ("WGSC_QUEUE_MAX_CONCURRENT", lambda raw: max(0, int(float(raw)))),
  "min_free_gpu_mb": ("WGSC_QUEUE_MIN_FREE_MB", lambda raw: max(0, int(float(raw)))),
  "probe_interval_seconds": ("WGSC_QUEUE_PROBE_INTERVAL", lambda raw: max(2, int(float(raw)))),
}


def load_queue_config() -> Dict[str, Any]:
  """queue.json over defaults, environment over queue.json; cached 5 seconds."""
  global _CONFIG_CACHE, _CONFIG_CACHE_AT
  now = time.time()
  if _CONFIG_CACHE is not None and now - _CONFIG_CACHE_AT < _CONFIG_CACHE_SECONDS:
    return dict(_CONFIG_CACHE)

  config = dict(_CONFIG_DEFAULTS)
  try:
    raw_text = _QUEUE_CONFIG_PATH.read_text(encoding="utf-8")
    file_config = json.loads(raw_text)
    if isinstance(file_config, dict):
      for key in _CONFIG_DEFAULTS:
        if key in file_config and file_config[key] is not None:
          config[key] = file_config[key]
  except FileNotFoundError:
    pass
  except Exception as exc:  # malformed config must not break submissions
    LOGGER.warning("Ignoring unreadable queue config %s: %s", _QUEUE_CONFIG_PATH, exc)

  for key, (env_name, converter) in _CONFIG_ENV_OVERRIDES.items():
    raw = os.environ.get(env_name, "")
    if str(raw).strip():
      try:
        config[key] = converter(raw)
      except (TypeError, ValueError):
        LOGGER.warning("Ignoring invalid %s=%r for queue config", env_name, raw)

  _CONFIG_CACHE = config
  _CONFIG_CACHE_AT = now
  return dict(config)


_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_CONFIG_CACHE_AT = 0.0


def queue_identity_key(remote_config: Dict[str, Any]) -> str:
  """Same identity the result-download code uses to pin a job to one server."""
  host = str(remote_config.get("host", "")).strip().lower()
  port = int(remote_config.get("port", 22) or 22)
  username = str(remote_config.get("username", "")).strip()
  output_root = str(remote_config.get("output_root", "")).strip().rstrip("/")
  return f"{username}@{host}:{port}::{output_root}"


class GpuLaunchGate:
  """Tracks waiting jobs per remote identity and grants launch slots.

  `occupying_provider` returns the live job registry values; a job counts as
  occupying while its status is "running" (covers queued-then-granted overlap
  via the internal granted set, removed by `launch_finished`).
  """

  def __init__(
    self,
    *,
    occupying_provider: Callable[[], List[Dict[str, Any]]],
    probe_fn: Callable[..., List[Dict[str, Any]]],
    clock: Callable[[], float] = time.time,
  ) -> None:
    self._occupying_provider = occupying_provider
    self._probe_fn = probe_fn
    self._clock = clock
    self._lock = threading.Lock()
    self._waiting: Dict[str, "OrderedDict[str, float]"] = {}
    self._granted: Dict[str, str] = {}  # job_id -> identity key
    self._probe_cache: Dict[str, Dict[str, Any]] = {}

  # ------------------------------------------------------------------ probe

  def _probe_snapshot(self, identity: str, remote_config: Dict[str, Any]) -> Dict[str, Any]:
    """Cached per identity: {"at", "gpus", "error"}; refreshed by probe_fn."""
    interval = max(2, int(load_queue_config().get("probe_interval_seconds", 20)))
    with self._lock:
      cached = self._probe_cache.get(identity)
      if cached and self._clock() - cached.get("at", 0.0) < interval:
        return cached
    # Probe outside the lock: SSH can block for seconds.
    try:
      gpus = self._probe_fn(remote_config=remote_config)
      snapshot = {"at": self._clock(), "gpus": gpus, "error": ""}
    except Exception as exc:
      # Keep the previous cards if any, but record the error (fail-open signal).
      snapshot = {
        "at": self._clock(),
        "gpus": list(cached.get("gpus", [])) if cached else [],
        "error": str(exc)[:300],
      }
      LOGGER.warning("GPU probe failed for %s: %s", identity, str(exc)[:200])
    with self._lock:
      self._probe_cache[identity] = snapshot
    return snapshot

  # ------------------------------------------------------------- capacity

  def _capacity(self, identity: str, snapshot: Dict[str, Any]) -> bool:
    """Decide whether one more launch fits. Callers must hold no assumptions
    about atomicity — the grant step re-checks under the lock."""
    config = load_queue_config()
    if not config.get("enabled", True):
      return True

    probe_error = str(snapshot.get("error", "")).strip()
    gpus = list(snapshot.get("gpus", []))

    if config.get("max_concurrent_jobs", 0) > 0:
      max_concurrent = int(config["max_concurrent_jobs"])
    elif gpus:
      max_concurrent = max(1, len(gpus))
    else:
      # No GPU count known and no explicit cap: fail open on the count gate.
      max_concurrent = 0

    if max_concurrent > 0:
      entries: Dict[str, tuple[str, str]] = {}
      for job in self._occupying_provider():
        remote = job.get("remote") if isinstance(job.get("remote"), dict) else {}
        entries[str(job.get("id", ""))] = (
          str(job.get("status", "")).strip().lower(),
          queue_identity_key(remote),
        )
      running = sum(
        1
        for status, job_identity in entries.values()
        if status == "running" and job_identity == identity
      )
      with self._lock:
        # Granted-but-not-yet-launched jobs still occupy their slot; jobs that
        # already flipped to "running" are counted above (no double count).
        running += sum(
          1
          for granted_id, granted_identity in self._granted.items()
          if granted_identity == identity and entries.get(granted_id, ("", ""))[0] == "queued"
        )
      if running >= max_concurrent:
        return False

    # Memory gate applies only when the probe is healthy; probe_error => open.
    min_free_mb = int(config.get("min_free_gpu_mb", 8000) or 0)
    if not probe_error and gpus and min_free_mb > 0:
      if not any(gpu.get("free_mb", 0) >= min_free_mb for gpu in gpus):
        return False
    return True

  # ---------------------------------------------------------------- queue

  def wait_for_slot(
    self,
    job: Dict[str, Any],
    remote_config: Dict[str, Any],
    *,
    persist_fn: Optional[Callable[[], None]] = None,
    note_fn: Optional[Callable[[str], None]] = None,
  ) -> bool:
    """Block the calling (runner) thread until a launch slot is granted.

    Returns True when granted (job["queue_state"] == "granted"; caller must
    call launch_finished after the launch attempt). Returns False when the job
    was canceled while waiting.
    """
    config = load_queue_config()
    if not config.get("enabled", True):
      return True
    identity = queue_identity_key(remote_config)
    job_id = str(job.get("id", ""))

    with self._lock:
      waiting = self._waiting.setdefault(identity, OrderedDict())
      waiting.pop(job_id, None)
      waiting[job_id] = self._clock()

    job["status"] = "queued"
    job["queue_state"] = "waiting"
    job["remote_stage"] = "queued_gpu"
    if note_fn:
      note_fn("Waiting for a free GPU slot (FIFO launch queue).")
    if persist_fn:
      persist_fn()

    try:
      while True:
        if job.get("cancel_requested"):
          job["status"] = "canceled"
          job["remote_stage"] = "canceled"
          job["queue_state"] = ""
          job.pop("queue_position", None)
          job["finished_at"] = self._clock()
          if note_fn:
            note_fn("Canceled while waiting in the launch queue.")
          if persist_fn:
            persist_fn()
          return False

        snapshot = self._probe_snapshot(identity, remote_config)
        position = self._refresh_position(job, identity, job_id)
        if self._capacity(identity, snapshot):
          with self._lock:
            waiting = self._waiting.get(identity, OrderedDict())
            head = next(iter(waiting), "")
            if head == job_id:
              waiting.pop(job_id, None)
              self._granted[job_id] = identity
              job["queue_state"] = "granted"
              job.pop("queue_position", None)
              if persist_fn:
                persist_fn()
              return True
        self._sleep(_WAIT_POLL_SECONDS)
    finally:
      with self._lock:
        waiting = self._waiting.get(identity)
        if waiting is not None:
          waiting.pop(job_id, None)
          if not waiting:
            self._waiting.pop(identity, None)

  def _sleep(self, seconds: float) -> None:
    # Instance method so tests can speed up the wait loop.
    time.sleep(seconds)

  def _refresh_position(self, job: Dict[str, Any], identity: str, job_id: str) -> int:
    with self._lock:
      waiting = self._waiting.get(identity, OrderedDict())
      position = 0
      for index, waiting_id in enumerate(waiting):
        if waiting_id == job_id:
          position = index + 1
          break
    if position:
      job["queue_position"] = position
    else:
      job.pop("queue_position", None)
    return position

  def launch_finished(self, job: Dict[str, Any]) -> None:
    """Release the granted-slot marker once the launch attempt is over (the
    job then counts as occupying through its own status, or is terminal)."""
    job_id = str(job.get("id", ""))
    with self._lock:
      self._granted.pop(job_id, None)

  def queue_position(self, job: Dict[str, Any], remote_config: Dict[str, Any]) -> int:
    identity = queue_identity_key(remote_config)
    job_id = str(job.get("id", ""))
    with self._lock:
      waiting = self._waiting.get(identity, OrderedDict())
      for index, waiting_id in enumerate(waiting):
        if waiting_id == job_id:
          return index + 1
    return 0

  def snapshot(self) -> Dict[str, Any]:
    """Debug/status view: waiting counts and last probe state per identity."""
    with self._lock:
      waiting_counts = {identity: len(entries) for identity, entries in self._waiting.items()}
      probes = {
        identity: {
          "age_seconds": round(self._clock() - entry.get("at", 0.0), 1),
          "gpus": entry.get("gpus", []),
          "error": entry.get("error", ""),
        }
        for identity, entry in self._probe_cache.items()
      }
    config = load_queue_config()
    return {"config": config, "waiting": waiting_counts, "probes": probes}
