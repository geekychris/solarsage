#!/usr/bin/env bash
# Install + configure Prometheus to scrape SolarSage's /metrics endpoint.
#
# Idempotent. Uses passwordless sudo where allowlisted; falls back to
# prompting for the /etc/prometheus/prometheus.yml write.

set -euo pipefail

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn\033[0m %s\n' "$*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log "Installing prometheus (apt-get)…"
# Passwordless sudoers here only matches the exact `apt-get update` and
# `apt-get -y install <pkg>` forms — no extra flags.
sudo -n apt-get update >/dev/null 2>&1 || true
sudo -n apt-get -y install prometheus >/dev/null
ok "prometheus installed"

log "Writing /etc/prometheus/prometheus.yml (needs sudo)…"
if sudo -n cp "$SCRIPT_DIR/prometheus.yml.example" /etc/prometheus/prometheus.yml 2>/dev/null; then
  ok "config installed (passwordless)"
else
  warn "passwordless sudo doesn't cover /etc writes"
  echo "  Run manually:"
  echo "    sudo cp $SCRIPT_DIR/prometheus.yml.example /etc/prometheus/prometheus.yml"
  echo "    sudo systemctl restart prometheus"
  exit 1
fi

log "Restarting prometheus…"
sudo systemctl restart prometheus
sleep 2
if sudo systemctl is-active --quiet prometheus; then
  ok "prometheus running"
else
  warn "prometheus didn't come up; check: sudo journalctl -u prometheus -n 30"
  exit 1
fi

log "Verifying scrape…"
sleep 5
if curl -sf "http://localhost:9090/api/v1/query?query=solarsage_battery_soc_percent" | grep -q "success"; then
  ok "Prometheus is scraping SolarSage's /metrics."
  echo
  echo "  Web UI:   http://localhost:9090"
  echo "  Metrics:  http://localhost:8000/metrics"
else
  warn "no data yet — first scrape may take up to 30 s; try again in a minute."
fi
