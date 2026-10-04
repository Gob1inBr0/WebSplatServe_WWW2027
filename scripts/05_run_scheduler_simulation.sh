#!/usr/bin/env bash
# 05_run_scheduler_simulation.sh — bash port of 05_run_scheduler_simulation.ps1
# Simulates one scheduling policy under one network condition, writing a trace CSV.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
SCENE_ID="scene_a"
POLICY="joint"
BANDWIDTH_MBPS=10
RTT_MS=60
MANIFEST=""
OUT_CSV=""

usage() {
  echo "Usage: $0 [--scene-id scene_a] [--policy naive|bandwidth|viewport|gpu|joint|full] [--bandwidth-mbps 10] [--rtt-ms 60] [--manifest PATH] [--out-csv PATH] [--python PATH]"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --scene-id) SCENE_ID="$2"; shift 2;;
    --policy) POLICY="$2"; shift 2;;
    --bandwidth-mbps) BANDWIDTH_MBPS="$2"; shift 2;;
    --rtt-ms) RTT_MS="$2"; shift 2;;
    --manifest) MANIFEST="$2"; shift 2;;
    --out-csv) OUT_CSV="$2"; shift 2;;
    --python) PYTHON="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$POLICY" in
  naive|bandwidth|viewport|gpu|joint|full) ;;
  *) echo "Invalid --policy: $POLICY (allowed: naive, bandwidth, viewport, gpu, joint, full)" >&2; exit 1;;
esac

if [ -z "$MANIFEST" ]; then
  MANIFEST="web/generated/websplatserve/$SCENE_ID/websplatserve_manifest.json"
fi
if [ ! -f "$MANIFEST" ]; then
  echo "Manifest not found: $MANIFEST. Run scripts/04_export_scene.sh first." >&2
  exit 1
fi

if [ -z "$OUT_CSV" ]; then
  OUT_CSV="web/generated/experiments/$SCENE_ID-$POLICY-trace.csv"
fi
mkdir -p "$(dirname "$OUT_CSV")"

echo "[05] Running scheduler simulation"
"$PYTHON" web/serving/adaptive_scheduler.py "$MANIFEST" --policy "$POLICY" --bandwidth-mbps "$BANDWIDTH_MBPS" --rtt-ms "$RTT_MS" --out-csv "$OUT_CSV"
echo "[05] Trace CSV: $OUT_CSV"
