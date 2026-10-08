"""Tests for the GPU launch queue: FIFO order, capacity gates, fail-open."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.server import gpu_queue  # noqa: E402
from web.server.gpu_queue import GpuLaunchGate, load_queue_config  # noqa: E402
from web.server.remote_executor import parse_gpu_report  # noqa: E402


def _fast_gate(occupying, probe_fn, **kwargs):
  gate = GpuLaunchGate(occupying_provider=occupying, probe_fn=probe_fn, **kwargs)
  gate._sleep = lambda seconds: time.sleep(min(seconds, 0.01))
  return gate


def _fresh_config(monkeypatch_dir: Path, overrides: dict | None = None) -> None:
  """Point the config at a temp file and reset the module-level cache."""
  config_path = monkeypatch_dir / "queue.json"
  if overrides is None:
    config_path.write_text("{}", encoding="utf-8")
  else:
    config_path.write_text(json.dumps(overrides), encoding="utf-8")
  gpu_queue._QUEUE_CONFIG_PATH = config_path
  gpu_queue._CONFIG_CACHE = None
  gpu_queue._CONFIG_CACHE_AT = 0.0


def _reload_config() -> dict:
  """load_queue_config bypassing the 5s cache (for tests that flip env/files)."""
  gpu_queue._CONFIG_CACHE = None
  gpu_queue._CONFIG_CACHE_AT = 0.0
  return load_queue_config()


_REMOTE = {"host": "gpu-server", "port": 22, "username": "root", "output_root": "/websplatserve/outputs"}
_REMOTE_OTHER = {"host": "other-server", "port": 22, "username": "root", "output_root": "/websplatserve/outputs"}


def _job(job_id: str, status: str = "queued", remote: dict | None = None) -> dict:
  return {"id": job_id, "status": status, "remote": dict(remote or _REMOTE)}


_ONE_GPU = [{"index": 0, "name": "A100", "used_mb": 1000, "total_mb": 80000, "free_mb": 79000, "utilization_pct": 10}]


# ------------------------------------------------------------------ parser

def test_gpu_report_parse_and_skip_malformed():
  raw = """0, NVIDIA A100-SXM4-80GB, 1234, 81920, 95
bad line without enough fields
1, NVIDIA A100, not_a_number, 81920, 50
2, RTX, 100, 24564, -3
"""
  gpus = parse_gpu_report(raw)
  assert [g["index"] for g in gpus] == [0, 2]
  assert gpus[0]["free_mb"] == 81920 - 1234
  # Negative utilization clamps to 0, free memory never negative.
  assert gpus[1]["utilization_pct"] == 0
  assert gpus[1]["free_mb"] == 24564 - 100
  assert parse_gpu_report("") == []


# ------------------------------------------------------------------- config

def test_config_env_overrides_and_disabled(tmp_path=None):
  import os, tempfile
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td))
    config = _reload_config()
    assert config["enabled"] is True
    assert config["max_concurrent_jobs"] == 0  # auto

    os.environ["WGSC_QUEUE_MAX_CONCURRENT"] = "3"
    try:
      config = _reload_config()
      assert config["max_concurrent_jobs"] == 3
    finally:
      os.environ.pop("WGSC_QUEUE_MAX_CONCURRENT", None)

    _fresh_config(Path(td), overrides={"max_concurrent_jobs": 5, "min_free_gpu_mb": 1000})
    config = _reload_config()
    assert config["max_concurrent_jobs"] == 5 and config["min_free_gpu_mb"] == 1000

    os.environ["WGSC_QUEUE_MAX_CONCURRENT"] = "not_a_number"
    try:
      # Invalid env value falls back to the file value.
      assert _reload_config()["max_concurrent_jobs"] == 5
    finally:
      os.environ.pop("WGSC_QUEUE_MAX_CONCURRENT", None)


# -------------------------------------------------------------- gate: basic

def _wait_granted(gate, job, remote, results, persist_calls):
  granted = gate.wait_for_slot(
    job, remote,
    persist_fn=lambda: persist_calls.append(1),
    note_fn=lambda text: None,
  )
  results.append(granted)


def test_fifo_first_job_granted_second_waits_then_succeeds():
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td))
    registry = {}

    def occupying():
      return list(registry.values())

    probe_calls = []
    def probe_fn(remote_config):
      probe_calls.append(1)
      return [dict(g) for g in _ONE_GPU]

    gate = _fast_gate(occupying, probe_fn)
    job1, job2 = _job("job-1"), _job("job-2")
    results, persist_calls = [], []

    thread1 = threading.Thread(target=_wait_granted, args=(gate, job1, _REMOTE, results, persist_calls))
    thread1.start()
    deadline = time.time() + 5
    while not results and time.time() < deadline:
      time.sleep(0.01)
    thread1.join(timeout=5)
    assert results == [True], "first job should be granted immediately"
    assert job1["queue_state"] == "granted"
    assert probe_calls, "probe should have run"

    # While job-1 is granted-but-launching (status still queued), job-2 queues.
    registry["job-1"] = job1
    thread2 = threading.Thread(target=_wait_granted, args=(gate, job2, _REMOTE, results, persist_calls))
    thread2.start()
    deadline = time.time() + 2
    while len(results) < 2 and time.time() < deadline:
      time.sleep(0.01)
    assert len(results) == 1, "job-2 must still be waiting"
    assert job2["status"] == "queued" and job2["queue_position"] == 1

    # Job-1 finishes its launch and reports running; the slot stays taken.
    gate.launch_finished(job1)
    job1["status"] = "running"
    time.sleep(0.2)
    assert len(results) == 1, "cap is one job per GPU; job-2 must wait"

    # Job-1 completes -> job-2 is granted.
    job1["status"] = "completed"
    thread2.join(timeout=5)
    assert results[-1] is True
    assert job2["queue_state"] == "granted"
    gate.launch_finished(job2)


def test_queue_position_orders_fifo():
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td))
    # Probe says zero free memory -> nobody launches; positions stay stable.
    busy_gpu = [dict(_ONE_GPU[0], free_mb=10)]

    def probe_fn(remote_config):
      return [dict(g) for g in busy_gpu]

    registry: dict = {}
    gate = _fast_gate(lambda: list(registry.values()), probe_fn)
    jobs = [_job(f"job-{i}") for i in range(1, 4)]
    results, persist_calls = [], []

    threads = [
      threading.Thread(target=_wait_granted, args=(gate, job, _REMOTE, results, persist_calls))
      for job in jobs
    ]
    for thread in threads:
      thread.start()
      time.sleep(0.05)
    time.sleep(0.3)
    assert results == [], "no GPU free: nobody may launch"
    assert [job.get("queue_position") for job in jobs] == [1, 2, 3]

    busy_gpu[0]["free_mb"] = 50000
    gate._probe_cache.clear()  # skip the 20s probe cache in the test
    for thread in threads:
      thread.join(timeout=10)
    assert results == [True, True, True], "all jobs launch in FIFO order once memory frees"


# ------------------------------------------------------------- gate: gates

def test_memory_threshold_blocks_and_fail_open_on_probe_error():
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td))
    calls = {"n": 0}

    def probe_fn(remote_config):
      calls["n"] += 1
      if calls["n"] == 1:
        return [dict(_ONE_GPU[0], free_mb=100)]  # below min_free_gpu_mb
      raise RuntimeError("nvidia-smi disappeared")

    registry: dict = {}
    gate = _fast_gate(lambda: list(registry.values()), probe_fn)
    job = _job("job-x")
    results, persist_calls = [], []
    thread = threading.Thread(target=_wait_granted, args=(gate, job, _REMOTE, results, persist_calls))
    thread.start()
    time.sleep(0.3)
    assert results == [], "low free memory must block the launch"

    # Probe now errors: fail-open — the launch proceeds count-only.
    gate._probe_cache.clear()  # skip the 20s probe cache in the test
    thread.join(timeout=10)
    assert results == [True], "broken probe must not freeze submissions"
    gate.launch_finished(job)


def test_identity_isolation_between_servers():
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td))
    # Server A: one busy GPU (no free memory). Server B: healthy.
    def probe_fn(remote_config):
      if remote_config["host"] == "gpu-server":
        return [dict(_ONE_GPU[0], free_mb=10)]
      return [dict(_ONE_GPU[0], free_mb=50000)]

    registry = {"busy": _job("busy", status="running")}
    gate = _fast_gate(lambda: list(registry.values()), probe_fn)
    job_a = _job("job-a")
    job_b = _job("job-b", remote=_REMOTE_OTHER)
    results, persist_calls = [], []
    thread_a = threading.Thread(target=_wait_granted, args=(gate, job_a, _REMOTE, results, persist_calls))
    thread_b = threading.Thread(target=_wait_granted, args=(gate, job_b, _REMOTE_OTHER, results, persist_calls))
    thread_a.start(); thread_b.start()
    thread_b.join(timeout=5)
    assert results == [True], "server B must be unaffected by server A's full GPU"
    time.sleep(0.2)
    assert job_a["status"] == "queued", "server A stays queued behind its busy GPU"
    assert job_a.get("queue_position") == 1
    job_a["cancel_requested"] = True
    thread_a.join(timeout=5)
    assert job_a["status"] == "canceled"


def test_auto_concurrency_cap_from_probe_gpu_count():
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td))  # max_concurrent_jobs = 0 (auto)
    two_gpus = [dict(_ONE_GPU[0]), dict(_ONE_GPU[0], index=1)]
    identity = "root@gpu-server:22::/websplatserve/outputs"
    snapshot = {"at": time.time(), "gpus": two_gpus, "error": ""}

    def probe_fn(remote_config):
      return [dict(g) for g in two_gpus]

    registry = {"a": _job("a", status="running")}
    gate = _fast_gate(lambda: list(registry.values()), probe_fn)
    # 1 running on 2 GPUs -> room; 2 running -> full; 3rd job -> still full.
    assert gate._capacity(identity, snapshot) is True
    registry["b"] = _job("b", status="running")
    assert gate._capacity(identity, snapshot) is False


def test_disabled_queue_grants_immediately():
  import os, tempfile
  with tempfile.TemporaryDirectory() as td:
    _fresh_config(Path(td), overrides={"enabled": False})
    gate = _fast_gate(lambda: [], lambda remote_config: (_ for _ in ()).throw(RuntimeError("no")))
    job = _job("job-off")
    granted = gate.wait_for_slot(job, _REMOTE)
    assert granted is True
    assert job.get("queue_state") is None and job.get("status") == "queued"


# ----------------------------------------------------- persisted-job recovery

def test_load_persisted_queued_job_marked_failed_after_restart():
  import tempfile
  from web.server import jobs as jobs_module

  with tempfile.TemporaryDirectory() as td:
    log_dir = Path(td) / "job_logs"
    job_dir = log_dir / "queued-job"  # state files live one level below the root
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(json.dumps({
      "id": "queued-job",
      "status": "queued",
      "remote_detached": False,
      "algorithm_family": "scaffold-gs",
    }), encoding="utf-8")

    original_dir = jobs_module.JOB_LOG_DIR
    original_jobs = dict(jobs_module.JOBS)
    jobs_module.JOB_LOG_DIR = log_dir
    try:
      jobs_module.load_persisted_jobs()
      loaded = jobs_module.JOBS.get("queued-job")
      assert loaded is not None
      assert loaded["status"] == "failed"
      assert "launch queue" in loaded["failure_reason"]
    finally:
      jobs_module.JOB_LOG_DIR = original_dir
      jobs_module.JOBS.clear()
      jobs_module.JOBS.update(original_jobs)


def main() -> int:
  tests = [
    test_gpu_report_parse_and_skip_malformed,
    test_config_env_overrides_and_disabled,
    test_fifo_first_job_granted_second_waits_then_succeeds,
    test_queue_position_orders_fifo,
    test_memory_threshold_blocks_and_fail_open_on_probe_error,
    test_identity_isolation_between_servers,
    test_auto_concurrency_cap_from_probe_gpu_count,
    test_disabled_queue_grants_immediately,
    test_load_persisted_queued_job_marked_failed_after_restart,
  ]
  failures = 0
  for test in tests:
    started = time.time()
    try:
      test()
      print(f"[ok] {test.__name__} ({time.time() - started:.2f}s)")
    except Exception as exc:
      failures += 1
      import traceback
      print(f"[FAIL] {test.__name__}: {exc}")
      traceback.print_exc()
  print(f"{len(tests) - failures}/{len(tests)} passed")
  return 1 if failures else 0


if __name__ == "__main__":
  raise SystemExit(main())
