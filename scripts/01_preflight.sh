#!/usr/bin/env bash
# 01_preflight.sh — bash port of 01_preflight.ps1
# Runs focused tests and syntax checks for the WebSplatServe serving layer.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
while [ $# -gt 0 ]; do
  case "$1" in
    --python) PYTHON="$2"; shift 2;;
    -h|--help) echo "Usage: $0 [--python PATH]"; exit 0;;
    *) echo "Unknown argument: $1" >&2; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[01] WebSplatServe preflight"
echo "Root: $ROOT"

if ! "$PYTHON" -c "" >/dev/null 2>&1; then
  echo "Python not found or not runnable: $PYTHON" >&2
  exit 1
fi
"$PYTHON" --version

echo "[01] Running focused tests"
"$PYTHON" web/tools/run_tests.py websplatserve telemetry web_export

echo "[01] Running syntax checks"
CACHE="${TMPDIR:-/tmp}/websplatserve_pycache"
mkdir -p "$CACHE"
"$PYTHON" -X "pycache_prefix=$CACHE" -m py_compile \
  web/serving/manifest.py \
  web/serving/adaptive_scheduler.py \
  web/serving/backend_profiles.py \
  web/tools/export_websplatserve_assets.py \
  web/tools/run_serving_benchmark.py \
  web/tools/collect_deployment_evidence.py \
  web/tools/test_websplatserve_manifest.py \
  web/tools/test_websplatserve_scheduler.py \
  web/server/telemetry.py \
  web/server/api_server.py

echo "[01] Preflight passed"
