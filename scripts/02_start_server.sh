#!/usr/bin/env bash
# 02_start_server.sh — bash port of 02_start_server.ps1
# Starts the WebSplatServe API server, or reuses one already listening on the port.
set -euo pipefail

PYTHON="${PYTHON:-python3}"
HOST="127.0.0.1"
PORT=8080
TOKEN=""

usage() {
  echo "Usage: $0 [--host 127.0.0.1] [--port 8080] [--token TOKEN] [--python PATH]"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --token) TOKEN="$2"; shift 2;;
    --python) PYTHON="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1;;
  esac
done
case "$PORT" in
  ''|*[!0-9]*) echo "Invalid --port: $PORT (must be a number)" >&2; exit 1;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[02] Starting WebSplatServe server"

if ! "$PYTHON" -c "" >/dev/null 2>&1; then
  echo "Python not found or not runnable: $PYTHON" >&2
  exit 1
fi

TOKEN_PATH="$ROOT/web/config/server.token"
TMP_TOKEN_PATH="${TMPDIR:-/tmp}/websplatserve_server.token"

# Strip BOM and whitespace: PowerShell 5.1's Set-Content -Encoding UTF8 writes
# a leading BOM that would corrupt the X-Auth-Token header.
clean_token() { tr -d '\357\273\277\ \t\r\n'; }

read_existing_token() {
  if [ -n "$TOKEN" ]; then return 0; fi
  if [ -f "$TOKEN_PATH" ]; then
    TOKEN="$(clean_token < "$TOKEN_PATH")"
    return 0
  fi
  if [ -f "$TMP_TOKEN_PATH" ]; then
    TOKEN="$(clean_token < "$TMP_TOKEN_PATH")"
  fi
}

port_listening() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  elif command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -q "[:.]$PORT " && return 0
  elif command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -E "[:.]$PORT[[:space:]].*LISTEN" >/dev/null && return 0
  else
    echo "[02] WARNING: none of lsof/ss/netstat found; cannot detect an already-running server." >&2
  fi
  return 1
}

health_check() {
  curl -fsS -H "X-Auth-Token: $TOKEN" "http://$HOST:$PORT/api/health" >/dev/null
}

if port_listening; then
  echo "[02] Port $PORT is already listening. Reusing existing server."
  read_existing_token
  if [ -z "$TOKEN" ]; then
    echo "Port $PORT is already in use, but no token was provided and no token file exists. Pass --token for the running server." >&2
    exit 1
  fi
  if ! health_check; then
    echo "Port $PORT is in use, but the available token was rejected. Pass --token for the running server or stop the existing process." >&2
    exit 1
  fi
  echo "[02] Health check passed"
  echo "[02] Console: http://$HOST:$PORT/web/console/"
  echo "[02] Token: $TOKEN"
  exit 0
fi

read_existing_token
if [ -z "$TOKEN" ]; then
  TOKEN="$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(24))')"
fi

if mkdir -p "$(dirname "$TOKEN_PATH")" && printf '%s' "$TOKEN" > "$TOKEN_PATH" 2>/dev/null; then
  chmod 600 "$TOKEN_PATH" 2>/dev/null || true
else
  if ! printf '%s' "$TOKEN" > "$TMP_TOKEN_PATH" 2>/dev/null; then
    echo "Could not write the token to $TOKEN_PATH or $TMP_TOKEN_PATH; pass --token explicitly next time." >&2
    exit 1
  fi
  echo "[02] Could not write web/config/server.token; wrote fallback token to $TMP_TOKEN_PATH"
fi

mkdir -p web/generated
LOG="web/generated/server.log"
nohup "$PYTHON" web/server/api_server.py --host "$HOST" --port "$PORT" --token "$TOKEN" >"$LOG" 2>&1 &
PID=$!
sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
  echo "[02] Server process $PID exited immediately; last log lines:" >&2
  tail -20 "$LOG" >&2
  exit 1
fi
echo "[02] Started python process id $PID (log: $LOG)"

if ! health_check; then
  echo "[02] Server did not become healthy on http://$HOST:$PORT; last log lines:" >&2
  tail -20 "$LOG" >&2
  kill "$PID" 2>/dev/null || true
  exit 1
fi
echo "[02] Health check passed"
echo "[02] Console: http://$HOST:$PORT/web/console/"
echo "[02] Token: $TOKEN"
