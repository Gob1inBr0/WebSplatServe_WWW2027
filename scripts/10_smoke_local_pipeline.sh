#!/usr/bin/env bash
# 10_smoke_local_pipeline.sh — bash port of 10_smoke_local_pipeline.ps1
# End-to-end smoke test in the system temp dir: synthetic PLY -> export -> simulation -> mini benchmark.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
ROWS=160
export PYTHON

usage() {
  echo "Usage: $0 [--rows 160] [--python PATH]"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --rows) ROWS="$2"; shift 2;;
    --python) PYTHON="$2"; export PYTHON; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SMOKE_ROOT="${TMPDIR:-/tmp}/websplatserve_smoke"
PLY_PATH="$SMOKE_ROOT/scene.ply"
OUT_DIR="$SMOKE_ROOT/assets"
TRACE_CSV="$SMOKE_ROOT/joint-trace.csv"
BENCH_CSV="$SMOKE_ROOT/serving-benchmark.csv"

mkdir -p "$SMOKE_ROOT"

echo "[10] Running local smoke pipeline in $SMOKE_ROOT"

SMOKE_PLY="$PLY_PATH" SMOKE_ROWS="$ROWS" "$PYTHON" - <<'PY'
import os
from pathlib import Path
from web.tools.test_web_export import write_test_ply

write_test_ply(Path(os.environ["SMOKE_PLY"]), int(os.environ["SMOKE_ROWS"]))
print(os.environ["SMOKE_PLY"])
PY

"$ROOT/scripts/04_export_scene.sh" \
  --ply "$PLY_PATH" \
  --scene-id smoke_temp \
  --out-dir "$OUT_DIR" \
  --backend-profile vanilla-3dgs-sh

MANIFEST="$OUT_DIR/websplatserve_manifest.json"

"$ROOT/scripts/05_run_scheduler_simulation.sh" \
  --scene-id smoke_temp \
  --manifest "$MANIFEST" \
  --out-csv "$TRACE_CSV" \
  --policy joint \
  --bandwidth-mbps 10 \
  --rtt-ms 60

"$ROOT/scripts/06_run_policy_benchmark.sh" \
  --scene-id smoke_temp \
  --manifest "$MANIFEST" \
  --out-csv "$BENCH_CSV" \
  --bandwidths "2,10" \
  --rtts "30"

echo "[10] Smoke pipeline passed"
echo "[10] PLY: $PLY_PATH"
echo "[10] Assets: $OUT_DIR"
echo "[10] Trace CSV: $TRACE_CSV"
echo "[10] Benchmark CSV: $BENCH_CSV"
