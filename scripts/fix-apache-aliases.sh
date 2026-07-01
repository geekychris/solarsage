#!/usr/bin/env bash
# Set the ServerAlias line in the SolarSage apache vhost to the
# canonical list (so localhost / pi5 / pi-ha etc. all serve SolarSage
# from the Pi's browser). Truly idempotent — safe to re-run from any
# state.

set -euo pipefail

CONF="/etc/apache2/sites-available/solarsage.conf"
CANONICAL="    ServerAlias pi-sf localhost pi5 pi5.hitorro.com pi-ha.hitorro.com"

if [[ ! -f "$CONF" ]]; then
  echo "not found: $CONF" >&2
  exit 1
fi

TMP="$(mktemp)"
# awk replaces every line that starts with any indent + "ServerAlias pi-sf"
# with the canonical alias line. Runs on the current file regardless of
# what state it's already in — so re-running after a botched sed still
# converges.
awk -v repl="$CANONICAL" '
  /^[[:space:]]*ServerAlias[[:space:]]+pi-sf([[:space:]]|$)/ {
    print repl
    next
  }
  { print }
' "$CONF" > "$TMP"

if diff -q "$CONF" "$TMP" >/dev/null 2>&1; then
  echo "aliases already canonical — nothing to do"
  rm -f "$TMP"
else
  sudo cp -a "$CONF" "$CONF.bak"
  sudo mv "$TMP" "$CONF"
  sudo chown root:root "$CONF"
  sudo chmod 644 "$CONF"
  echo "updated $CONF (backup at $CONF.bak)"
fi

echo "--- ServerAlias lines now ---"
grep -n ServerAlias "$CONF"

echo "--- configtest ---"
sudo apache2ctl configtest 2>&1 | grep -v 'AH00558' || true

echo "--- reload ---"
sudo systemctl reload apache2
echo "done"
