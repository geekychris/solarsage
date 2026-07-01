#!/usr/bin/env bash
# Grant the current user passwordless sudo for restarting the
# SolarSage services only. Scoped — sudo still prompts for everything
# else.

set -euo pipefail

RUN_USER="${RUN_USER:-$(id -un)}"
TARGET="/etc/sudoers.d/solarsage-restart"

RULE="$RUN_USER ALL=(ALL) NOPASSWD: \
/bin/systemctl restart solarsage-backend.service, \
/bin/systemctl reload solarsage-backend.service, \
/bin/systemctl status solarsage-backend.service, \
/bin/systemctl restart solarsage-frontend.service, \
/bin/systemctl reload apache2"

echo "$RULE" | sudo tee "$TARGET" >/dev/null
sudo chmod 440 "$TARGET"
sudo visudo -c
echo "Wrote $TARGET."
