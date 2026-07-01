#!/usr/bin/env bash
# Deploy latest SolarSage to this machine.
#
# Runs from the SolarSage repo root; safe to re-run.
#
# Usage:
#   ./scripts/deploy.sh                # pull, install deps, restart backend
#   ./scripts/deploy.sh --no-restart   # just pull + install
#   ./scripts/deploy.sh --frontend     # also rebuild the frontend bundle

set -euo pipefail

RESTART=1
FRONTEND_BUILD=0

for arg in "$@"; do
  case "$arg" in
    --no-restart) RESTART=0 ;;
    --frontend)   FRONTEND_BUILD=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Resolve repo root (script sits in scripts/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mfail\033[0m %s\n' "$*"; exit 1; }

log "Fetching latest code…"
git fetch origin
git pull --ff-only

BACKEND_VENV="$REPO_ROOT/backend/.venv"
if [[ ! -d "$BACKEND_VENV" ]]; then
  log "Creating backend virtualenv…"
  python3 -m venv "$BACKEND_VENV"
fi

log "Refreshing Python dependencies…"
"$BACKEND_VENV/bin/pip" install --quiet -r "$REPO_ROOT/backend/requirements.txt"

if [[ "$FRONTEND_BUILD" == "1" ]]; then
  log "Rebuilding frontend bundle…"
  ( cd "$REPO_ROOT/frontend" && npm install --silent && npm run build --silent )
fi

if [[ "$RESTART" == "1" ]]; then
  if systemctl list-units --full -all 2>/dev/null | grep -q solarsage-backend.service; then
    log "Restarting solarsage-backend.service…"
    if sudo -n systemctl restart solarsage-backend.service 2>/dev/null; then
      ok "backend restarted (passwordless sudo)"
    else
      warn "no passwordless sudo — trying interactive"
      sudo systemctl restart solarsage-backend.service
    fi
    sleep 3
    STATUS="$(systemctl is-active solarsage-backend.service || true)"
    if [[ "$STATUS" == "active" ]]; then
      ok "backend is active"
    else
      fail "backend not active after restart (state=$STATUS)"
    fi
  else
    warn "solarsage-backend.service not installed — use ./scripts/install-systemd.sh"
  fi
fi

ok "Deploy complete: $(git log --oneline -1)"
