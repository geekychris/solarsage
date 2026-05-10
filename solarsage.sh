#!/usr/bin/env bash
# Multi-command launcher: `solarsage <start|stop|status|logs|update>`
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-status}"
case "$cmd" in
  start)   "$DIR/start.sh" ;;
  stop)    "$DIR/stop.sh" ;;
  status)  "$DIR/status.sh" ;;
  restart) "$DIR/stop.sh"; sleep 1; "$DIR/start.sh" ;;
  logs)
    svc="${2:-backend}"
    if [[ "$svc" != "backend" && "$svc" != "frontend" ]]; then
      echo "usage: solarsage logs [backend|frontend]"; exit 1
    fi
    tail -F "$DIR/.run/$svc.log"
    ;;
  update)
    git -C "$DIR" pull --ff-only
    ( cd "$DIR/backend" && .venv/bin/pip install -q -r requirements.txt )
    ( cd "$DIR/frontend" && npm install --silent && npm run build --silent )
    echo "updated to $(git -C "$DIR" rev-parse --short HEAD)"
    ;;
  *)
    echo "usage: solarsage <start|stop|status|restart|logs|update>"; exit 1
    ;;
esac
