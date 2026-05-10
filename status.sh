#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pidof() { lsof -ti ":$1" 2>/dev/null || true; }

bp=$(pidof 8000); fp=$(pidof 5173)
printf '  backend  (:8000)  '
if [[ -n "$bp" ]]; then printf 'running  pid %s\n' "$bp"; else printf 'stopped\n'; fi
printf '  frontend (:5173)  '
if [[ -n "$fp" ]]; then printf 'running  pid %s\n' "$fp"; else printf 'stopped\n'; fi

if [[ -n "$bp" ]]; then
  echo
  echo "  health:  $(curl -sS http://127.0.0.1:8000/api/health 2>/dev/null || echo unreachable)"
  echo "  sessions:$(curl -sS http://127.0.0.1:8000/api/auth/status 2>/dev/null || echo '?')"
fi
echo
echo "logs: $DIR/.run/{backend,frontend}.log"
