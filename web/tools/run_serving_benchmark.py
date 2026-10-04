#!/usr/bin/env python3
"""Run policy/network simulations for WebSplatServe manifests."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from web.serving.adaptive_scheduler import POLICIES, simulate_manifest  # noqa: E402
from web.serving.manifest import load_manifest  # noqa: E402

CSV_FIELDS = [
  "policy", "bandwidth_mbps", "rtt_ms",
  "ttfr_ms", "load_ms", "bytes", "rows", "chunks",
  "quality_gain", "quality_fraction", "view_gain_fraction", "t50_view_ms", "t90_view_ms",
  "stopped_early", "budget_skips",
  "vertex_count", "memory_budget_rows", "gpu_capacity_rows", "quality_target",
]


def parse_list(value: str, cast, option: str):
  items = [item.strip() for item in value.split(",") if item.strip()]
  if not items:
    raise SystemExit(f"error: {option} must contain at least one value")
  try:
    return [cast(item) for item in items]
  except ValueError:
    raise SystemExit(f"error: {option} has an invalid value: {value}")


def main() -> int:
  parser = argparse.ArgumentParser(description="Benchmark WebSplatServe scheduling policies over network conditions.")
  parser.add_argument("manifest")
  parser.add_argument("--policies", default=",".join(POLICIES))
  parser.add_argument("--bandwidths", default="2,5,10,30,100")
  parser.add_argument("--rtts", default="30,120")
  parser.add_argument("--memory-budget-rows", type=int, default=2_000_000)
  parser.add_argument("--gpu-capacity-rows", type=int, default=900_000)
  parser.add_argument("--quality-target", type=float, default=0.9)
  parser.add_argument("--out", default="web/generated/experiments/serving_benchmark.csv")
  args = parser.parse_args()

  manifest = load_manifest(args.manifest)
  policies = parse_list(args.policies, str, "--policies")
  bandwidths = parse_list(args.bandwidths, float, "--bandwidths")
  rtts = parse_list(args.rtts, float, "--rtts")
  for policy in policies:
    if policy not in POLICIES:
      raise SystemExit(f"error: unknown policy: {policy} (allowed: {', '.join(POLICIES)})")

  vertex_count = manifest.get("vertexCount", "")
  rows = []
  for policy in policies:
    for bandwidth in bandwidths:
      for rtt in rtts:
        result = simulate_manifest(
          manifest,
          policy=policy,
          bandwidth_mbps=bandwidth,
          rtt_ms=rtt,
          memory_budget_rows=args.memory_budget_rows,
          gpu_capacity_rows=args.gpu_capacity_rows,
          quality_target=args.quality_target,
        )
        rows.append({
          "policy": policy,
          "bandwidth_mbps": bandwidth,
          "rtt_ms": rtt,
          "ttfr_ms": result["ttfr_ms"],
          "load_ms": result["load_ms"],
          "bytes": result["bytes"],
          "rows": result["rows"],
          "chunks": result["chunks"],
          "quality_gain": result["quality_gain"],
          "quality_fraction": result["quality_fraction"],
          "view_gain_fraction": result["view_gain_fraction"],
          "t50_view_ms": result["t50_view_ms"],
          "t90_view_ms": result["t90_view_ms"],
          "stopped_early": result["stopped_early"],
          "budget_skips": result["budget_skips"],
          "vertex_count": vertex_count,
          "memory_budget_rows": args.memory_budget_rows,
          "gpu_capacity_rows": args.gpu_capacity_rows,
          "quality_target": args.quality_target,
        })

  out_path = Path(args.out)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with open(out_path, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
  print(json.dumps({"out": str(out_path), "rows": len(rows)}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
