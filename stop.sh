#!/usr/bin/env bash
# Stop both SolarSage servers.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for svc in backend frontend; do
  pid_file="$DIR/.run/${svc}.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    kill "$(cat "$pid_file")" && echo "stopped $svc"
    rm -f "$pid_file"
  fi
done
# Belt + braces: kill anything still bound to the ports
lsof -ti :8000 -ti :5173 2>/dev/null | xargs -r kill 2>/dev/null || true
echo "SolarSage stopped"
