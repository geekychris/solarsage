#!/usr/bin/env bash
# Restore a SolarSage DB backup.
#
# Usage:
#   ./scripts/restore.sh ~/solarsage-backups/eg4_history_2026-06-30_10-00-00.db

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup.db>" >&2
  exit 2
fi

SRC="$1"

if [[ ! -f "$SRC" ]]; then
  echo "not found: $SRC" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="${DB_PATH:-$REPO_ROOT/backend/eg4_history.db}"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }

log "Stopping backend so we can replace the DB safely…"
if systemctl list-units --full -all 2>/dev/null | grep -q solarsage-backend.service; then
  sudo systemctl stop solarsage-backend.service || warn "stop failed"
else
  warn "solarsage-backend.service not installed — assuming backend is not running"
fi

# Snapshot current DB before overwriting
if [[ -f "$DB_PATH" ]]; then
  SIDE="$DB_PATH.pre-restore-$(date +%s)"
  cp -a "$DB_PATH" "$SIDE"
  ok "current DB preserved at $SIDE"
fi

log "Copying backup → $DB_PATH"
cp -a "$SRC" "$DB_PATH"
# Owner + perms match what the backend expects
if command -v chown >/dev/null; then
  # If run as root, restore ownership to the invoking user
  if [[ $EUID -eq 0 ]] && [[ -n "${SUDO_USER:-}" ]]; then
    chown "$SUDO_USER:$SUDO_USER" "$DB_PATH"
  fi
fi

if systemctl list-units --full -all 2>/dev/null | grep -q solarsage-backend.service; then
  log "Starting backend back up…"
  sudo systemctl start solarsage-backend.service
  sleep 3
  systemctl is-active solarsage-backend.service && ok "backend is active" || warn "backend not active"
fi

ok "restore complete from $SRC"
