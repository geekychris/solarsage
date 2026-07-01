#!/usr/bin/env bash
# Configure MQTT publish + Home Assistant discovery. Interactive.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/backend/.env"

cat <<EOF
==============================================================
SolarSage — MQTT publish + HA discovery setup
==============================================================

Publishes each widget's state to an MQTT broker + registers a
Home Assistant discovery config so widgets appear as HA sensors
automatically.

Details: docs/MQTT.md

==============================================================
EOF

read -rp "MQTT broker host or IP: " BROKER
if [[ -z "$BROKER" ]]; then
  echo "broker required" >&2
  exit 1
fi

read -rp "Port [1883]: " PORT
PORT="${PORT:-1883}"

read -rp "Username (blank for anonymous): " USER
if [[ -n "$USER" ]]; then
  read -rsp "Password: " PASS
  echo
fi

read -rp "Base topic [solarsage]: " BASE
BASE="${BASE:-solarsage}"

read -rp "HA discovery prefix [homeassistant]: " DISCO
DISCO="${DISCO:-homeassistant}"

echo
echo "--- probing broker (TCP only, not auth) ---"
if command -v nc >/dev/null 2>&1; then
  if nc -z -w 3 "$BROKER" "$PORT" 2>/dev/null; then
    echo "  ✓ $BROKER:$PORT reachable"
  else
    echo "  ✗ $BROKER:$PORT not reachable — check network / firewall"
    read -rp "Save anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 1
  fi
else
  echo "  (skipped — no 'nc' available)"
fi

if [[ -f "$ENV_FILE" ]]; then
  grep -v -E '^(MQTT_BROKER|MQTT_PORT|MQTT_USER|MQTT_PASS|MQTT_BASE_TOPIC|MQTT_DISCOVERY_PREFIX)=' \
    "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
fi
{
  echo
  echo "# MQTT publish + Home Assistant discovery (see docs/MQTT.md)"
  echo "MQTT_BROKER=$BROKER"
  echo "MQTT_PORT=$PORT"
  if [[ -n "$USER" ]]; then
    echo "MQTT_USER=$USER"
    echo "MQTT_PASS=$PASS"
  fi
  echo "MQTT_BASE_TOPIC=$BASE"
  echo "MQTT_DISCOVERY_PREFIX=$DISCO"
} >> "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo
echo "Wrote $ENV_FILE"
echo
echo "Restart backend:"
echo "  sudo systemctl restart solarsage-backend.service"
echo
echo "After the first widget refresh (< 60s), HA → Devices & Services"
echo "should show a 'SolarSage' device with one sensor per widget."
