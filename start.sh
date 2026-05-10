#!/usr/bin/env bash
# Start both SolarSage servers in the background.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DIR/.run"

# Backend
if ! lsof -ti :8000 >/dev/null 2>&1; then
  ( cd "$DIR/backend" && \
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 \
      > "$DIR/.run/backend.log" 2>&1 & echo $! > "$DIR/.run/backend.pid" )
  echo "started backend (pid $(cat "$DIR/.run/backend.pid"))"
else
  echo "backend already running on :8000"
fi

# Frontend
if ! lsof -ti :5173 >/dev/null 2>&1; then
  ( cd "$DIR/frontend" && \
    npm run dev -- --host 127.0.0.1 --port 5173 \
      > "$DIR/.run/frontend.log" 2>&1 & echo $! > "$DIR/.run/frontend.pid" )
  echo "started frontend (pid $(cat "$DIR/.run/frontend.pid"))"
else
  echo "frontend already running on :5173"
fi

# Wait briefly for the backend to come up before printing the URL
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then break; fi
  sleep 0.5
done
echo
echo "SolarSage running:"
echo "  UI       http://127.0.0.1:5173"
echo "  API docs http://127.0.0.1:8000/docs"
echo "  logs     $DIR/.run/{backend,frontend}.log"
