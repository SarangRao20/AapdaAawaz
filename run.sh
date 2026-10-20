#!/usr/bin/env bash
# Runs the FastAPI backend (:8000) and the Vite frontend (:5173) together. Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"

PY=""
for v in .venv venv; do
  [ -x "$ROOT/backend/$v/bin/python" ] && PY="$ROOT/backend/$v/bin/python" && break
done
if [ -z "$PY" ]; then
  echo "No virtualenv found in backend/.venv or backend/venv. Create one:" >&2
  echo "  cd backend && python -m venv venv && venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$ROOT/frontend" && npm install)
fi

pids=()
cleanup() {
  trap - INT TERM EXIT
  echo; echo "Stopping..."
  for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

(cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$API_PORT") 2>&1 | sed -u 's/^/[api] /' &
pids+=($!)
(cd "$ROOT/frontend" && exec npm run dev -- --host "$HOST" --port "$UI_PORT") 2>&1 | sed -u 's/^/[ui]  /' &
pids+=($!)

echo "API: http://$HOST:$API_PORT/docs    UI: http://$HOST:$UI_PORT"
wait -n || true
