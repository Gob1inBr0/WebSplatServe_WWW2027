#!/usr/bin/env bash
# 08_export_deployment_evidence.sh — bash port of 08_export_deployment_evidence.ps1
# Downloads the anonymous telemetry deployment evidence as markdown.
set -euo pipefail

HOST="127.0.0.1"
PORT=8080
TOKEN=""
OUT="deployment_evidence.md"

usage() {
  echo "Usage: $0 [--host 127.0.0.1] [--port 8080] [--token TOKEN] [--out deployment_evidence.md]"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --token) TOKEN="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -z "$TOKEN" ]; then
  TOKEN_PATH="$ROOT/web/config/server.token"
  TMP_TOKEN_PATH="${TMPDIR:-/tmp}/websplatserve_server.token"
  if [ -f "$TOKEN_PATH" ]; then
    TOKEN="$(tr -d ' \t\r\n' < "$TOKEN_PATH")"
  elif [ -f "$TMP_TOKEN_PATH" ]; then
    TOKEN="$(tr -d ' \t\r\n' < "$TMP_TOKEN_PATH")"
  else
    echo "Token was not provided and web/config/server.token does not exist. Run scripts/02_start_server.sh first." >&2
    exit 1
  fi
fi

URI="http://$HOST:$PORT/api/telemetry/evidence.md"
echo "[08] Exporting deployment evidence from $URI"
curl -fsS -H "X-Auth-Token: $TOKEN" "$URI" -o "$OUT"
echo "[08] Wrote $OUT"
