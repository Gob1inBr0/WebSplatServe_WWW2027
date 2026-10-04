"""Resource-aware chunk scheduler used by WebSplatServe experiments.

The implementation is deliberately explainable rather than learning based:
each policy in the WWW evaluation maps to the same candidate chunks and differs
only by which resource signals it is allowed to use.

Simulation semantics (v2):
- the base layer is always delivered first; TTFR is the base completion time;
- policies stop once the cumulative visual gain reaches ``quality_target`` of
  the total gain, except ``full`` which downloads everything as the
  non-progressive baseline;
- chunks that would push resident rows past ``memory_budget_rows`` are skipped
  and reported via ``budget_skips``;
- frame time/fps are re-estimated after every chunk from resident rows versus
  ``gpu_capacity_rows``, so the gpu/joint policies actually observe rendering
  pressure inside the simulation;
- decode/GPU costs enter the score as byte equivalents at the current
  bandwidth (decode weighted lambdaDecode=8x, GPU weighted muGpu=2x).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

from web.serving.manifest import load_manifest, normalize_manifest

POLICIES = ("naive", "bandwidth", "viewport", "gpu", "joint", "full")

GPU_GUARD_P95_MS = 34.0
GPU_GUARD_LOW_FPS = 24.0
LAMBDA_DECODE = 8.0
MU_GPU = 2.0


@dataclass
class ClientState:
  bandwidth_mbps: float = 10.0
  rtt_ms: float = 40.0
  fps: float = 60.0
  p95_frame_ms: float = 16.7
  target_fps: float = 60.0
  memory_budget_rows: int = 2_000_000
  gpu_capacity_rows: int = 900_000
  resident_rows: int = 0
  throughput_bytes_per_ms: float | None = None
  camera_velocity: float = 0.0
  viewport_forward: tuple[float, float, float] = (0.0, 0.0, -1.0)
  camera_position: tuple[float, float, float] = (0.0, 0.0, 4.0)

  def byte_equivalent_per_ms(self) -> float:
    if self.throughput_bytes_per_ms is not None:
      return float(self.throughput_bytes_per_ms)
    return 1.0

  def update_render_pressure(self) -> None:
    """Re-estimate frame time from resident rows versus GPU capacity."""
    capacity = max(1, int(self.gpu_capacity_rows))
    ratio = self.resident_rows / capacity
    if ratio <= 1.0:
      self.p95_frame_ms = 1000.0 / max(1.0, self.target_fps)
      self.fps = float(self.target_fps)
    else:
      self.fps = float(self.target_fps) / ratio
      self.p95_frame_ms = 1000.0 / max(0.1, self.fps)


def _norm3(value: Iterable[float]) -> tuple[float, float, float]:
  vals = list(value)[:3]
  while len(vals) < 3:
    vals.append(0.0)
  mag = math.sqrt(sum(v * v for v in vals)) or 1.0
  return (vals[0] / mag, vals[1] / mag, vals[2] / mag)


def _chunk_center(chunk: dict[str, Any]) -> tuple[float, float, float] | None:
  region = chunk.get("region")
  if not isinstance(region, dict):
    return None
  center = region.get("center")
  if not isinstance(center, list) or len(center) < 3:
    return None
  return (float(center[0]), float(center[1]), float(center[2]))


def view_weight(chunk: dict[str, Any], state: ClientState) -> float:
  center = _chunk_center(chunk)
  if center is None:
    return 1.0
  forward = _norm3(state.viewport_forward)
  to_chunk = _norm3((
    center[0] - state.camera_position[0],
    center[1] - state.camera_position[1],
    center[2] - state.camera_position[2],
  ))
  dot = sum(a * b for a, b in zip(forward, to_chunk))
  base = max(0.05, (dot + 1.0) / 2.0)
  if state.camera_velocity > 0.6:
    return max(0.25, base * 0.75)
  return base


def score_chunk(chunk: dict[str, Any], state: ClientState, policy: str = "joint") -> float:
  if policy not in POLICIES:
    raise ValueError(f"unknown policy: {policy}")
  if policy == "naive":
    return -float(chunk.get("ordinal", 0))
  if policy == "full":
    return 1.0

  bytes_cost = max(1.0, float(chunk.get("transferBytes", chunk.get("bytes", 1))))
  gain = max(0.001, float(chunk.get("visualGain", chunk.get("gain", chunk.get("rows", 1)))))
  equiv = state.byte_equivalent_per_ms()
  decode_cost = float(chunk.get("decodeCostMs", 0.0)) * equiv
  gpu_cost = float(chunk.get("gpuCostMs", 0.0)) * equiv
  weight = 1.0

  if policy in ("viewport", "joint"):
    weight *= view_weight(chunk, state)
  if policy in ("gpu", "joint"):
    if state.p95_frame_ms > GPU_GUARD_P95_MS or state.fps < GPU_GUARD_LOW_FPS:
      weight *= 0.25
    projected_rows = state.resident_rows + int(chunk.get("rows", 0) or 0)
    if projected_rows > state.memory_budget_rows:
      weight *= 0.01
  if policy == "bandwidth":
    return gain / bytes_cost
  if policy == "viewport":
    return gain * weight / bytes_cost
  if policy == "gpu":
    return gain * weight / (bytes_cost + MU_GPU * gpu_cost)
  return gain * weight / (bytes_cost + LAMBDA_DECODE * decode_cost + MU_GPU * gpu_cost)


def select_chunks(
  manifest: dict[str, Any],
  state: ClientState,
  *,
  policy: str = "joint",
  pending_ids: set[str] | None = None,
  max_chunks: int = 4,
) -> list[dict[str, Any]]:
  normalized = normalize_manifest(manifest)
  pending = [
    chunk for chunk in normalized["chunks"]
    if pending_ids is None or str(chunk["id"]) in pending_ids
  ]
  if policy == "full":
    return pending
  pending.sort(key=lambda chunk: score_chunk(chunk, state, policy), reverse=True)
  return pending[:max(1, int(max_chunks))]


def _pick_next(
  normalized: dict[str, Any],
  state: ClientState,
  *,
  policy: str,
  pending_ids: set[str],
) -> dict[str, Any] | None:
  """One selection step shared by the simulation loop.

  The base layer always wins while it is pending; ``full`` keeps manifest
  order; everything else sorts by the policy score.
  """
  pending = [c for c in normalized["chunks"] if str(c["id"]) in pending_ids]
  if not pending:
    return None
  for chunk in pending:
    if chunk.get("type") == "base":
      return chunk
  if policy == "full":
    return pending[0]
  return max(pending, key=lambda chunk: score_chunk(chunk, state, policy))


def simulate_manifest(
  manifest: dict[str, Any],
  *,
  policy: str = "joint",
  bandwidth_mbps: float = 10.0,
  rtt_ms: float = 40.0,
  memory_budget_rows: int = 2_000_000,
  gpu_capacity_rows: int = 900_000,
  quality_target: float = 0.9,
) -> dict[str, Any]:
  if policy not in POLICIES:
    raise ValueError(f"unknown policy: {policy}")
  if bandwidth_mbps <= 0:
    raise ValueError("bandwidth_mbps must be positive")
  if rtt_ms < 0:
    raise ValueError("rtt_ms must be non-negative")
  if not 0.0 < quality_target <= 1.0:
    raise ValueError("quality_target must be in (0, 1]")

  normalized = normalize_manifest(manifest)
  chunks = normalized["chunks"]
  pending_ids = {str(chunk["id"]) for chunk in chunks}
  total_gain = sum(float(chunk.get("visualGain", 0.0)) for chunk in chunks)
  # Viewpoint-weighted quality: gain scaled by how much of the chunk lies in
  # the current view frustum (camera held fixed during the simulation). This
  # is what lets viewport-aware policies win on time-to-usable-quality even
  # when byte counts coincide.
  state0 = ClientState(
    viewport_forward=(0.0, 0.0, -1.0),
    camera_position=(0.0, 0.0, 4.0),
  )
  view_weights = {str(chunk["id"]): view_weight(chunk, state0) for chunk in chunks}
  total_view_gain = sum(
    float(chunk.get("visualGain", 0.0)) * view_weights[str(chunk["id"])] for chunk in chunks
  )
  state = ClientState(
    bandwidth_mbps=bandwidth_mbps,
    rtt_ms=rtt_ms,
    memory_budget_rows=memory_budget_rows,
    gpu_capacity_rows=gpu_capacity_rows,
    throughput_bytes_per_ms=bandwidth_mbps * 1_000_000 / 8 / 1000,
  )

  trace = []
  time_ms = 0.0
  bytes_done = 0
  rows_done = 0
  quality_gain = 0.0
  view_gain = 0.0
  budget_skips = 0
  ttfr_ms = None
  t50_view_ms = None
  t90_view_ms = None
  base_delivered = False

  def _cross(threshold: float) -> bool:
    return total_view_gain > 0 and view_gain >= threshold * total_view_gain

  while pending_ids:
    chunk = _pick_next(normalized, state, policy=policy, pending_ids=pending_ids)
    if chunk is None:
      break
    chunk_id = str(chunk["id"])
    is_base = chunk.get("type") == "base"

    if not is_base and rows_done + int(chunk.get("rows", 0) or 0) > memory_budget_rows:
      pending_ids.remove(chunk_id)
      budget_skips += 1
      continue

    pending_ids.remove(chunk_id)
    transfer_ms = float(rtt_ms) + float(chunk["transferBytes"]) / state.throughput_bytes_per_ms
    decode_ms = float(chunk.get("decodeCostMs", 0.0))
    time_ms += transfer_ms + decode_ms
    bytes_done += int(chunk["transferBytes"])
    rows_done += int(chunk["rows"])
    chunk_gain = float(chunk.get("visualGain", 0.0))
    quality_gain += chunk_gain
    view_gain += chunk_gain * view_weights[chunk_id]
    state.resident_rows = rows_done
    state.update_render_pressure()
    if is_base:
      base_delivered = True
    if ttfr_ms is None and (base_delivered or rows_done > 0):
      ttfr_ms = round(time_ms, 2)
    if t50_view_ms is None and _cross(0.5):
      t50_view_ms = round(time_ms, 2)
    if t90_view_ms is None and _cross(0.9):
      t90_view_ms = round(time_ms, 2)
    trace.append({
      "time_ms": round(time_ms, 2),
      "chunk_id": chunk_id,
      "stage": "base" if is_base else "refinement",
      "policy": policy,
      "bytes": bytes_done,
      "rows": rows_done,
      "quality_gain": round(quality_gain, 4),
      "view_gain": round(view_gain, 4),
    })

    if policy != "full" and total_gain > 0 and quality_gain >= quality_target * total_gain:
      break

  delivered_gain_fraction = quality_gain / total_gain if total_gain > 0 else 1.0
  delivered_view_fraction = view_gain / total_view_gain if total_view_gain > 0 else 1.0
  return {
    "policy": policy,
    "bandwidth_mbps": bandwidth_mbps,
    "rtt_ms": rtt_ms,
    "quality_target": quality_target,
    "memory_budget_rows": memory_budget_rows,
    "gpu_capacity_rows": gpu_capacity_rows,
    "ttfr_ms": ttfr_ms,
    "load_ms": round(time_ms, 2),
    "bytes": bytes_done,
    "rows": rows_done,
    "chunks": len(trace),
    "total_chunks": len(chunks),
    "quality_gain": round(quality_gain, 4),
    "total_quality_gain": round(total_gain, 4),
    "quality_fraction": round(min(1.0, delivered_gain_fraction), 4),
    "view_gain_fraction": round(min(1.0, delivered_view_fraction), 4),
    "t50_view_ms": t50_view_ms,
    "t90_view_ms": t90_view_ms,
    "stopped_early": len(trace) < len(chunks),
    "budget_skips": budget_skips,
    "trace": trace,
  }


def write_trace_csv(simulation: dict[str, Any], path: str | Path) -> None:
  target = Path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  rows = simulation.get("trace", [])
  with open(target, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=["time_ms", "chunk_id", "stage", "policy", "bytes", "rows", "quality_gain", "view_gain"])
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
  parser = argparse.ArgumentParser(description="Simulate WebSplatServe adaptive chunk scheduling.")
  parser.add_argument("manifest")
  parser.add_argument("--policy", choices=POLICIES, default="joint")
  parser.add_argument("--bandwidth-mbps", type=float, default=10.0)
  parser.add_argument("--rtt-ms", type=float, default=40.0)
  parser.add_argument("--memory-budget-rows", type=int, default=2_000_000)
  parser.add_argument("--gpu-capacity-rows", type=int, default=900_000)
  parser.add_argument("--quality-target", type=float, default=0.9)
  parser.add_argument("--out-json", default="")
  parser.add_argument("--out-csv", default="")
  args = parser.parse_args()

  result = simulate_manifest(
    load_manifest(args.manifest),
    policy=args.policy,
    bandwidth_mbps=args.bandwidth_mbps,
    rtt_ms=args.rtt_ms,
    memory_budget_rows=args.memory_budget_rows,
    gpu_capacity_rows=args.gpu_capacity_rows,
    quality_target=args.quality_target,
  )
  if args.out_json:
    Path(args.out_json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
  if args.out_csv:
    write_trace_csv(result, args.out_csv)
  keys = ("policy", "ttfr_ms", "load_ms", "bytes", "rows", "chunks", "quality_fraction", "view_gain_fraction", "t50_view_ms", "t90_view_ms", "stopped_early", "budget_skips")
  print(json.dumps({k: result[k] for k in keys}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
