#!/usr/bin/env bash
# 09_run_all_local_checks.sh — bash port of 09_run_all_local_checks.ps1
# Runs the full local check set (currently: 01 preflight).
set -euo pipefail

PYTHON="${PYTHON:-python3}"
while [ $# -gt 0 ]; do
  case "$1" in
    --python) PYTHON="$2"; shift 2;;
    -h|--help) echo "Usage: $0 [--python PATH]"; exit 0;;
    *) echo "Unknown argument: $1" >&2; exit 1;;
  esac
done
export PYTHON

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[09] Running all local checks"
bash "$ROOT/scripts/01_preflight.sh"
echo "[09] Local checks passed"
