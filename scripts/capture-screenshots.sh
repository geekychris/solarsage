#!/usr/bin/env bash
# Convenience wrapper for tools/capture-screenshots.mjs.
#
# One-time setup:
#   cd $(dirname $0)/../frontend
#   npm install --save-dev playwright
#   npx playwright install chromium
#
# Then run this script with the SolarSage URL + credentials as env vars.
# It writes fresh PNGs into docs/screenshots/ and updates manifest.json.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ -z "${EG4_USERNAME:-}" ] || [ -z "${EG4_PASSWORD:-}" ]; then
  echo "Set EG4_USERNAME and EG4_PASSWORD in the environment." >&2
  echo "  export EG4_USERNAME=you"
  echo "  export EG4_PASSWORD=xxx"
  exit 2
fi

: "${SOLARSAGE_URL:=https://pi-sf.hitorro.com}"
export SOLARSAGE_URL

cd frontend
if [ ! -d node_modules/playwright ]; then
  echo "==> Installing playwright locally…"
  npm install --save-dev playwright
  npx playwright install chromium
fi
cd ..
node tools/capture-screenshots.mjs
