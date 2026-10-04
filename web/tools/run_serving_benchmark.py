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


def parse_list(value: str, cast):
  return [cast(item.strip()) for item in value.split(",") if item.strip()]


def main() -> int:
  parser = argparse.ArgumentParser(description="Benchmark WebSplatServe scheduling policies over network conditions.")
  parser.add_argument("manifest")
  parser.add_argument("--policies", default=",".join(POLICIES))
  parser.add_argument("--bandwidths", default="2,5,10,30,100")
  parser.add_argument("--rtts", default="30,120")
  parser.add_argument("--memory-budget-rows", type=int, default=2_000_000)
  parser.add_argument("--out", default="web/generated/experiments/serving_benchmark.csv")
  args = parser.parse_args()

  manifest = load_manifest(args.manifest)
  policies = parse_list(args.policies, str)
  bandwidths = parse_list(args.bandwidths, float)
  rtts = parse_list(args.rtts, float)
  rows = []
  for policy in policies:
    if policy not in POLICIES:
      raise ValueError(f"unknown policy: {policy}")
    for bandwidth in bandwidths:
      for rtt in rtts:
        result = simulate_manifest(
          manifest,
          policy=policy,
          bandwidth_mbps=bandwidth,
          rtt_ms=rtt,
          memory_budget_rows=args.memory_budget_rows,
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
        })

  out_path = Path(args.out)
  out_path.parent.mkdir(parents=True, exist_ok=True)
  with open(out_path, "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
  print(json.dumps({"out": str(out_path), "rows": len(rows)}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

