#!/usr/bin/env python3
"""Convert telemetry summary JSON into a paper-ready deployment note."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def fmt_stat(stat: dict) -> str:
  if not isinstance(stat, dict) or not stat.get("count"):
    return "n/a"
  return f"n={stat.get('count')}, p50={stat.get('p50')}, p95={stat.get('p95')}, max={stat.get('max')}"


def build_markdown(summary: dict) -> str:
  serving = summary.get("serving", {})
  http = summary.get("http", {})
  clients = summary.get("clients", {})
  lines = [
    "# WebSplatServe Deployment Evidence",
    "",
    "This note is generated from anonymous telemetry summary data.",
    "",
    "## Operational Scale",
    f"- Total events: {summary.get('events_total', 0)}",
    f"- Uptime seconds: {summary.get('uptime_seconds', 0)}",
    f"- HTTP requests: {http.get('requests', 0)}",
    f"- HTTP bytes served: {http.get('bytes_served', 0)}",
    f"- HTTP latency: {fmt_stat(http.get('latency_ms', {}))}",
    "",
    "## Serving Quality",
    f"- Scene loads: {serving.get('loads', 0)}",
    f"- Loads by stage: {json.dumps(serving.get('loads_by_stage', {}), ensure_ascii=False)}",
    f"- Failure rate: {serving.get('failure_rate', 0)}",
    f"- Unique clients: {serving.get('unique_clients', 0)}",
    f"- Benchmark loads: {serving.get('benchmark_loads', 0)}",
    f"- TTFR ms: {fmt_stat(serving.get('ttfr_ms', {}))}",
    f"- P95 frame time ms: {fmt_stat(serving.get('p95_frame_ms', {}))}",
    f"- FPS: {fmt_stat(serving.get('fps', {}))}",
    f"- Bytes per load: {fmt_stat(serving.get('bytes', {}))}",
    f"- Adaptation: up={serving.get('adaptation', {}).get('loads_adapted_up', 0)} loads, "
    f"down={serving.get('adaptation', {}).get('loads_adapted_down', 0)} loads, "
    f"cap p50 {serving.get('adaptation', {}).get('cap_initial', {}).get('p50', 'n/a')} -> "
    f"{serving.get('adaptation', {}).get('cap_final', {}).get('p50', 'n/a')} rows",
    f"- Policy counts: {json.dumps(serving.get('by_policy', {}), ensure_ascii=False)}",
    f"- Client profile counts: {json.dumps(serving.get('by_client_profile', {}), ensure_ascii=False)}",
    f"- Capability counts: {json.dumps(serving.get('by_capability', {}), ensure_ascii=False)}",
    f"- Scene scale counts: {json.dumps(serving.get('by_scene_scale', {}), ensure_ascii=False)}",
    f"- Failure stages: {json.dumps(serving.get('failures_by_stage', {}), ensure_ascii=False)}",
    "",
    "## Client Mix",
    f"- Browser: {json.dumps(clients.get('browser', {}), ensure_ascii=False)}",
    f"- OS: {json.dumps(clients.get('os', {}), ensure_ascii=False)}",
    f"- Device: {json.dumps(clients.get('device', {}), ensure_ascii=False)}",
  ]
  return "\n".join(lines) + "\n"


def main() -> int:
  parser = argparse.ArgumentParser(description="Build a deployment evidence markdown note from telemetry summary JSON.")
  parser.add_argument("summary_json")
  parser.add_argument("--out", default="deployment_evidence.md")
  args = parser.parse_args()
  summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
  Path(args.out).write_text(build_markdown(summary), encoding="utf-8")
  print(json.dumps({"out": args.out}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
