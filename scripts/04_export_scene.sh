#!/usr/bin/env bash
# 04_export_scene.sh — bash port of 04_export_scene.ps1
# Exports a 3DGS PLY into manifest + base layer + refinement chunks.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
PLY=""
SCENE_ID="scene_a"
OUT_DIR=""
BACKEND_PROFILE="vanilla-3dgs-sh"

usage() {
  echo "Usage: $0 --ply /path/to/scene.ply [--scene-id scene_a] [--out-dir DIR] [--backend-profile vanilla-3dgs-sh|compressed-decoded-sh|compact-pruned-sh] [--python PATH]"
  echo "The PLY path may also be given as the first positional argument."
}

while [ $# -gt 0 ]; do
  case "$1" in
    --ply) PLY="$2"; shift 2;;
    --scene-id) SCENE_ID="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --backend-profile) BACKEND_PROFILE="$2"; shift 2;;
    --python) PYTHON="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) if [ -z "$PLY" ]; then PLY="$1"; shift; else echo "Unknown argument: $1" >&2; usage >&2; exit 1; fi;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

case "$BACKEND_PROFILE" in
  vanilla-3dgs-sh|compressed-decoded-sh|compact-pruned-sh) ;;
  *) echo "Invalid --backend-profile: $BACKEND_PROFILE (allowed: vanilla-3dgs-sh, compressed-decoded-sh, compact-pruned-sh)" >&2; exit 1;;
esac

if [ -z "$PLY" ]; then
  echo "Missing required PLY path." >&2
  usage >&2
  exit 1
fi
if [ ! -f "$PLY" ]; then
  echo "PLY file not found: $PLY" >&2
  exit 1
fi

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="web/generated/websplatserve/$SCENE_ID"
fi

echo "[04] Exporting $PLY"
echo "[04] Output: $OUT_DIR"
"$PYTHON" web/tools/export_websplatserve_assets.py "$PLY" "$OUT_DIR" --backend-profile "$BACKEND_PROFILE"

DEFAULT_OUT="web/generated/websplatserve/$SCENE_ID"
if [ "$OUT_DIR" = "$DEFAULT_OUT" ]; then
  echo "[04] Viewer manifest: /web/generated/websplatserve/$SCENE_ID/manifest.json"
  echo "[04] Enriched manifest: web/generated/websplatserve/$SCENE_ID/websplatserve_manifest.json"
else
  echo "[04] Viewer manifest file: $OUT_DIR/manifest.json"
  echo "[04] Enriched manifest file: $OUT_DIR/websplatserve_manifest.json"
fi
