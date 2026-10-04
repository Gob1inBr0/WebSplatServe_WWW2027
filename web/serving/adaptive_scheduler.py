"""Resource-aware chunk scheduler used by WebSplatServe experiments.

The implementation is deliberately explainable rather than learning based:
each policy in the WWW evaluation maps to the same candidate chunks and differs
only by which resource signals it is allowed to use.
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


@dataclass
class ClientState:
  bandwidth_mbps: float = 10.0
  rtt_ms: float = 40.0
  fps: float = 60.0
  p95_frame_ms: float = 16.7
  memory_budget_rows: int = 2_000_000
  resident_rows: int = 0
  camera_velocity: float = 0.0
  viewport_forward: tuple[float, float, float] = (0.0, 0.0, -1.0)
  camera_position: tuple[float, float, float] = (0.0, 0.0, 4.0)


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
  decode_cost = float(chunk.get("decodeCostMs", 0.0))
  gpu_cost = float(chunk.get("gpuCostMs", 0.0))
  weight = 1.0

  if policy in ("viewport", "joint"):
    weight *= view_weight(chunk, state)
  if policy in ("gpu", "joint"):
    if state.p95_frame_ms > 34 or state.fps < 24:
      weight *= 0.25
    projected_rows = state.resident_rows + int(chunk.get("rows", 0) or 0)
    if projected_rows > state.memory_budget_rows:
      weight *= 0.01
  if policy == "bandwidth":
    return gain / bytes_cost
  if policy == "viewport":
    return gain * weight / bytes_cost
  if policy == "gpu":
    return gain * weight / (bytes_cost + 2.0 * gpu_cost)
  return gain * weight / (bytes_cost + 8.0 * decode_cost + 2.0 * gpu_cost)


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


def simulate_manifest(
  manifest: dict[str, Any],
  *,
  policy: str = "joint",
  bandwidth_mbps: float = 10.0,
  rtt_ms: float = 40.0,
  memory_budget_rows: int = 2_000_000,
) -> dict[str, Any]:
  normalized = normalize_manifest(manifest)
  pending_ids = {str(chunk["id"]) for chunk in normalized["chunks"]}
  state = ClientState(
    bandwidth_mbps=bandwidth_mbps,
    rtt_ms=rtt_ms,
    memory_budget_rows=memory_budget_rows,
  )
  trace = []
  time_ms = 0.0
  bytes_done = 0
  rows_done = 0
  quality_gain = 0.0
  ttfr_ms = None
  throughput_bytes_per_ms = max(1.0, bandwidth_mbps * 1_000_000 / 8 / 1000)

  while pending_ids:
    batch = select_chunks(normalized, state, policy=policy, pending_ids=pending_ids, max_chunks=1)
    if not batch:
      break
    chunk = batch[0]
    pending_ids.remove(str(chunk["id"]))
    transfer_ms = float(rtt_ms) + float(chunk["transferBytes"]) / throughput_bytes_per_ms
    decode_ms = float(chunk.get("decodeCostMs", 0.0))
    time_ms += transfer_ms + decode_ms
    bytes_done += int(chunk["transferBytes"])
    rows_done += int(chunk["rows"])
    quality_gain += float(chunk.get("visualGain", 0.0))
    state.resident_rows = rows_done
    if ttfr_ms is None and rows_done > 0:
      ttfr_ms = round(time_ms, 2)
    trace.append({
      "time_ms": round(time_ms, 2),
      "chunk_id": chunk["id"],
      "policy": policy,
      "bytes": bytes_done,
      "rows": rows_done,
      "quality_gain": round(quality_gain, 4),
    })
  return {
    "policy": policy,
    "bandwidth_mbps": bandwidth_mbps,
    "rtt_ms": rtt_ms,
    "ttfr_ms": ttfr_ms,
    "load_ms": round(time_ms, 2),
    "bytes": bytes_done,
    "rows": rows_done,
    "chunks": len(trace),
    "trace": trace,
  }


def write_trace_csv(simulation: dict[str, Any], path: str | Path) -> None:
  target = Path(path)
  target.parent.mkdir(parents=True, exist_ok=True)
  rows = simulation.get("trace", [])
  with open(target, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=["time_ms", "chunk_id", "policy", "bytes", "rows", "quality_gain"])
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
  parser = argparse.ArgumentParser(description="Simulate WebSplatServe adaptive chunk scheduling.")
  parser.add_argument("manifest")
  parser.add_argument("--policy", choices=POLICIES, default="joint")
  parser.add_argument("--bandwidth-mbps", type=float, default=10.0)
  parser.add_argument("--rtt-ms", type=float, default=40.0)
  parser.add_argument("--memory-budget-rows", type=int, default=2_000_000)
  parser.add_argument("--out-json", default="")
  parser.add_argument("--out-csv", default="")
  args = parser.parse_args()

  result = simulate_manifest(
    load_manifest(args.manifest),
    policy=args.policy,
    bandwidth_mbps=args.bandwidth_mbps,
    rtt_ms=args.rtt_ms,
    memory_budget_rows=args.memory_budget_rows,
  )
  if args.out_json:
    Path(args.out_json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
  if args.out_csv:
    write_trace_csv(result, args.out_csv)
  print(json.dumps({k: result[k] for k in ("policy", "ttfr_ms", "load_ms", "bytes", "rows", "chunks")}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
