#!/usr/bin/env bash
# 07_print_browser_benchmark_urls.sh — bash port of 07_print_browser_benchmark_urls.ps1
# Prints viewer and browser QoE benchmark URLs for manual browser runs.
set -euo pipefail

SCENE_ID="scene_a"
HOST="127.0.0.1"
PORT=8080
SECONDS_ARG=12
while [ $# -gt 0 ]; do
  case "$1" in
    --scene-id) SCENE_ID="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --seconds) SECONDS_ARG="$2"; shift 2;;
    *) echo "Unknown argument: $1" >&2; exit 1;;
  esac
done

MANIFEST_URL="/web/generated/websplatserve/$SCENE_ID/manifest.json"

echo "[07] Browser URLs"
echo "Viewer:"
echo "http://$HOST:$PORT/web/viewers/progressive.html?url=$MANIFEST_URL&policy=joint&profile=auto"
echo ""
echo "Browser QoE benchmark:"
echo "http://$HOST:$PORT/web/viewers/benchmark.html?url=$MANIFEST_URL&seconds=$SECONDS_ARG"
echo ""
echo "This benchmark records TTFR, bytes, resident rows, chunk arrivals, FPS/P95, client profile, capability, and failures."
echo "It does not run PSNR/SSIM/LPIPS or image-quality evaluation."
