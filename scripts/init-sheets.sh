#!/usr/bin/env bash
# Interactive walkthrough: wire up Google Sheets sync.
#
# Not fully automated (GCP setup happens in the browser) but writes the
# .env for you once you have the JSON key and sheet ID.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/backend/.env"
KEY_DEST="$HOME/.config/solarsage-sheets.json"

cat <<EOF
================================================================
SolarSage — Google Sheets sync setup
================================================================

This script writes the two env vars into $ENV_FILE and moves your
downloaded service-account key into place.

Before running this, complete these steps in your browser:

  1. Create a Google Sheet at https://sheets.google.com
     Add tabs: Contacts, Shopping, Todo, Border Log, Bookmarks,
               Starred Phrases (headers auto-materialize)

  2. Create a Google Cloud project at
     https://console.cloud.google.com

     Enable "Google Sheets API", then create a Service Account, then
     make a JSON key.

  3. Share the sheet with the service account email address (Editor).

Full walkthrough: $REPO_ROOT/docs/SHEETS.md

================================================================
EOF

read -rp "Path to the downloaded JSON key: " KEY_SRC
KEY_SRC="${KEY_SRC/#\~/$HOME}"
if [[ ! -f "$KEY_SRC" ]]; then
  echo "not found: $KEY_SRC" >&2
  exit 1
fi

read -rp "Google Sheet ID (from the URL): " SHEET_ID
if [[ -z "$SHEET_ID" ]]; then
  echo "sheet ID required" >&2
  exit 1
fi

mkdir -p "$(dirname "$KEY_DEST")"
cp -a "$KEY_SRC" "$KEY_DEST"
chmod 600 "$KEY_DEST"

# Remove any prior sheet lines in .env, then append the new ones
if [[ -f "$ENV_FILE" ]]; then
  grep -v -E '^(GOOGLE_APPLICATION_CREDENTIALS|SOLARSAGE_SHEET_ID)=' \
    "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
fi
{
  echo
  echo "# Google Sheets sync"
  echo "GOOGLE_APPLICATION_CREDENTIALS=$KEY_DEST"
  echo "SOLARSAGE_SHEET_ID=$SHEET_ID"
} >> "$ENV_FILE"

echo
echo "Wrote:"
echo "  key:    $KEY_DEST (mode 600)"
echo "  env:    $ENV_FILE"
echo
echo "Restart the backend to pick up the new config:"
echo "  sudo systemctl restart solarsage-backend.service"
