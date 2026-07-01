#!/usr/bin/env bash
# Add ServerAlias entries to the SolarSage apache vhost so localhost,
# pi5, and pi-ha etc. all serve SolarSage from the Pi's browser.
#
# Idempotent — safe to re-run.

set -euo pipefail

CONF="/etc/apache2/sites-available/solarsage.conf"
NEW_ALIASES="ServerAlias pi-sf localhost pi5 pi5.hitorro.com pi-ha.hitorro.com"

if [[ ! -f "$CONF" ]]; then
  echo "not found: $CONF" >&2
  exit 1
fi

if grep -qF "$NEW_ALIASES" "$CONF"; then
  echo "aliases already present — nothing to do"
else
  # sed -i.bak keeps a backup at $CONF.bak the first time we touch it
  sudo sed -i.bak "s|ServerAlias pi-sf$|    $NEW_ALIASES|" "$CONF"
  # normalize the indent (sed replaces the whole line contents; the
  # original had 4-space indent, keep it)
  sudo sed -i "s|^    *    ServerAlias pi-sf localhost|    $NEW_ALIASES|g" "$CONF"
  echo "updated $CONF"
fi

echo "--- ServerAlias lines now ---"
grep -n ServerAlias "$CONF"

echo "--- configtest ---"
sudo apache2ctl configtest 2>&1 | grep -v 'AH00558'

echo "--- reload ---"
sudo systemctl reload apache2
echo "done"
