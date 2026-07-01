#!/usr/bin/env bash
# Install systemd units for the SolarSage backend + frontend on a
# Debian/Raspberry Pi OS host. Idempotent.
#
# After running this, enable + start:
#   sudo systemctl enable --now solarsage-backend.service
#   sudo systemctl enable --now solarsage-frontend.service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_USER="${RUN_USER:-$(id -un)}"

BACKEND_SERVICE="/etc/systemd/system/solarsage-backend.service"
FRONTEND_SERVICE="/etc/systemd/system/solarsage-frontend.service"

if [[ $EUID -ne 0 ]] && ! sudo -n true 2>/dev/null; then
  echo "This script writes to /etc/systemd; re-run with sudo." >&2
  exit 1
fi

sudo tee "$BACKEND_SERVICE" >/dev/null <<EOF
[Unit]
Description=SolarSage backend (FastAPI/uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_ROOT/backend
Environment=PYTHONUNBUFFERED=1
ExecStart=$REPO_ROOT/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee "$FRONTEND_SERVICE" >/dev/null <<EOF
[Unit]
Description=SolarSage frontend (Vite dev server)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_ROOT/frontend
Environment=NODE_ENV=production
ExecStart=/usr/bin/env npm run dev -- --host 0.0.0.0 --port 5173
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
echo "Wrote $BACKEND_SERVICE and $FRONTEND_SERVICE."
echo "Enable + start with:"
echo "  sudo systemctl enable --now solarsage-backend.service solarsage-frontend.service"
