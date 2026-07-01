#!/usr/bin/env bash
# Backup the SolarSage SQLite DB + backend/.env.
#
# Usage:
#   ./scripts/backup.sh                     # default: ~/solarsage-backups/
#   BACKUP_DIR=/mnt/nas ./scripts/backup.sh
#   RETAIN_DAYS=30 ./scripts/backup.sh      # prune older backups

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

BACKUP_DIR="${BACKUP_DIR:-$HOME/solarsage-backups}"
RETAIN_DAYS="${RETAIN_DAYS:-14}"
DB_PATH="${DB_PATH:-$REPO_ROOT/backend/eg4_history.db}"

mkdir -p "$BACKUP_DIR"

TS="$(date +'%Y-%m-%d_%H-%M-%S')"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m ok\033[0m %s\n' "$*"; }

if [[ ! -f "$DB_PATH" ]]; then
  echo "DB not found: $DB_PATH" >&2
  exit 1
fi

# Use sqlite3's .backup so the copy is atomic even under active writes.
DB_OUT="$BACKUP_DIR/eg4_history_$TS.db"
if command -v sqlite3 >/dev/null; then
  log "sqlite3 .backup → $DB_OUT"
  sqlite3 "$DB_PATH" ".backup '$DB_OUT'"
else
  log "sqlite3 not found — cp -a (may be inconsistent if backend is writing)"
  cp -a "$DB_PATH" "$DB_OUT"
fi

# Also snapshot the .env — it holds api keys + sheets creds path
if [[ -f "$REPO_ROOT/backend/.env" ]]; then
  cp -a "$REPO_ROOT/backend/.env" "$BACKUP_DIR/env_$TS"
fi

# Prune old
if [[ -n "$RETAIN_DAYS" && "$RETAIN_DAYS" -gt 0 ]]; then
  log "Pruning backups older than $RETAIN_DAYS days…"
  find "$BACKUP_DIR" -type f \( -name 'eg4_history_*.db' -o -name 'env_*' \) \
       -mtime "+$RETAIN_DAYS" -delete
fi

ok "wrote $DB_OUT ($(du -h "$DB_OUT" | cut -f1))"
ok "kept the last $RETAIN_DAYS days in $BACKUP_DIR"
