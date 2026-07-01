#!/usr/bin/env bash
# Wire up Home Assistant integration (Telegram + other HA notify
# services). Interactive.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/backend/.env"

cat <<EOF
==============================================================
SolarSage — Home Assistant integration setup
==============================================================

This wires the 'telegram' notification channel (used by
subscription rules) to a service on your Home Assistant.

Before running this, you'll need a long-lived HA access token:

  HA UI → profile (bottom-left) → Security tab
        → Long-lived access tokens → Create Token
        → name it "SolarSage" → copy it (shown once)

Details: docs/NOTIFICATIONS.md

==============================================================
EOF

DEFAULT_URL="http://homeassistant.local:8123"
read -rp "HA base URL [$DEFAULT_URL]: " HA_URL
HA_URL="${HA_URL:-$DEFAULT_URL}"

read -rp "HA long-lived access token: " HA_TOKEN
if [[ -z "$HA_TOKEN" ]]; then
  echo "token required" >&2
  exit 1
fi

read -rp "HA service to call (e.g. telegram_bot.send_message, notify.persistent_notification) [telegram_bot.send_message]: " SVC
SVC="${SVC:-telegram_bot.send_message}"

read -rp "Default target (Telegram chat_id, HA entity_id list, or blank): " TARGET

# Test the token before writing
echo
echo "--- probing HA ---"
code=$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $HA_TOKEN" \
  "$HA_URL/api/" --max-time 5 || echo "-")
if [[ "$code" != "200" ]]; then
  echo "  HTTP $code from $HA_URL/api/ — token or URL may be wrong."
  read -rp "Save anyway? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || exit 1
else
  echo "  ✓ HA reachable, token accepted"
fi

# Wipe any prior HA_ / NOTIFY_TELEGRAM_ lines then append the new ones
if [[ -f "$ENV_FILE" ]]; then
  grep -v -E '^(HA_URL|HA_TOKEN|NOTIFY_TELEGRAM_SERVICE|NOTIFY_TELEGRAM_TARGET)=' \
    "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
fi
{
  echo
  echo "# Home Assistant integration (see docs/NOTIFICATIONS.md)"
  echo "HA_URL=$HA_URL"
  echo "HA_TOKEN=$HA_TOKEN"
  echo "NOTIFY_TELEGRAM_SERVICE=$SVC"
  if [[ -n "$TARGET" ]]; then
    echo "NOTIFY_TELEGRAM_TARGET=$TARGET"
  fi
} >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo
echo "Wrote $ENV_FILE"
echo
echo "Restart backend to pick up new config:"
echo "  sudo systemctl restart solarsage-backend.service"
echo
echo "Then test via:"
echo "  curl -sSk -X POST https://<host>/api/notify/test \\"
echo "    -H 'X-API-Key: <key>' -H 'Content-Type: application/json' \\"
echo "    -d '{\"type\":\"telegram\",\"text\":\"hello\"}'"
