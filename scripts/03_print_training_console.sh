#!/usr/bin/env bash
# 03_print_training_console.sh — bash port of 03_print_training_console.ps1
# Prints the remote training console URL. The console itself is used in a browser.
set -euo pipefail

HOST="127.0.0.1"
PORT=8080
while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    *) echo "Unknown argument: $1" >&2; exit 1;;
  esac
done

echo "[03] Remote training entrypoint"
echo "Open: http://$HOST:$PORT/web/console/"
echo ""
echo "Use this step when you do not already have a standard SH PLY."
echo "Training needs a remote GPU server, algorithm repo path, workspace root, output root, and adapter selection."
echo "If you already have a standard SH PLY, skip to scripts/04_export_scene.sh."
