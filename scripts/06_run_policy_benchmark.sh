#!/usr/bin/env bash
# 06_run_policy_benchmark.sh — bash port of 06_run_policy_benchmark.ps1
# Runs all scheduling policies across bandwidth/RTT settings, writing one benchmark CSV.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
SCENE_ID="scene_a"
POLICIES="full,naive,bandwidth,viewport,gpu,joint"
BANDWIDTHS="2,5,10,30,100"
RTTS="30,120"
MANIFEST=""
OUT_CSV=""

usage() {
  echo "Usage: $0 [--scene-id scene_a] [--policies full,naive,...] [--bandwidths 2,5,10,30,100] [--rtts 30,120] [--manifest PATH] [--out-csv PATH] [--python PATH]"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --scene-id) SCENE_ID="$2"; shift 2;;
    --policies) POLICIES="$2"; shift 2;;
    --bandwidths) BANDWIDTHS="$2"; shift 2;;
    --rtts) RTTS="$2"; shift 2;;
    --manifest) MANIFEST="$2"; shift 2;;
    --out-csv) OUT_CSV="$2"; shift 2;;
    --python) PYTHON="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -z "$MANIFEST" ]; then
  MANIFEST="web/generated/websplatserve/$SCENE_ID/websplatserve_manifest.json"
fi
if [ ! -f "$MANIFEST" ]; then
  echo "Manifest not found: $MANIFEST. Run scripts/04_export_scene.sh first." >&2
  exit 1
fi

if [ -z "$OUT_CSV" ]; then
  OUT_CSV="web/generated/experiments/$SCENE_ID-serving-benchmark.csv"
fi
mkdir -p "$(dirname "$OUT_CSV")"

echo "[06] Running policy/network benchmark"
"$PYTHON" web/tools/run_serving_benchmark.py "$MANIFEST" --policies "$POLICIES" --bandwidths "$BANDWIDTHS" --rtts "$RTTS" --out "$OUT_CSV"
echo "[06] Benchmark CSV: $OUT_CSV"
