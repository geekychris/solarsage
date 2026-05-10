#!/usr/bin/env bash
# SolarSage installer — macOS & Linux.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/geekychris/solarsage/main/install.sh | bash
#
# Or, with options:
#   curl -fsSL .../install.sh | INSTALL_DIR=~/code/solarsage bash
#
# The script is idempotent; re-running upgrades in place.

set -euo pipefail

REPO_URL="${SOLARSAGE_REPO:-https://github.com/geekychris/solarsage.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/solarsage}"
BRANCH="${SOLARSAGE_BRANCH:-main}"

BLUE=$'\033[1;34m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; RED=$'\033[1;31m'; RESET=$'\033[0m'
log()  { printf '%s==>%s %s\n' "$BLUE" "$RESET" "$*"; }
ok()   { printf '%s ok %s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s warn%s %s\n' "$YELLOW" "$RESET" "$*"; }
fail() { printf '%sfail%s %s\n' "$RED" "$RESET" "$*"; exit 1; }

# --- prereqs ----------------------------------------------------------------
need_cmd() { command -v "$1" >/dev/null 2>&1 || return 1; }

ensure_brew() {
  if ! need_cmd brew; then
    log "Homebrew not found — installing (you'll see its prompt)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
}

install_macos() {
  ensure_brew
  for pkg in git node python@3.11; do
    if ! brew list "$pkg" >/dev/null 2>&1; then
      log "Installing $pkg via brew"
      brew install "$pkg"
    fi
  done
}

install_linux() {
  if need_cmd apt-get; then
    log "Installing prerequisites via apt"
    sudo apt-get update
    sudo apt-get install -y git python3 python3-venv python3-pip nodejs npm
  elif need_cmd dnf; then
    log "Installing prerequisites via dnf"
    sudo dnf install -y git python3 python3-pip nodejs npm
  elif need_cmd pacman; then
    log "Installing prerequisites via pacman"
    sudo pacman -S --noconfirm git python python-pip nodejs npm
  else
    fail "unsupported Linux distro — install git, python3 ≥3.9, nodejs ≥18 manually then re-run"
  fi
}

log "SolarSage installer starting"
case "$(uname -s)" in
  Darwin) install_macos ;;
  Linux)  install_linux ;;
  *)      fail "unsupported OS: $(uname -s)" ;;
esac
need_cmd git    || fail "git missing after install"
need_cmd python3|| fail "python3 missing after install"
need_cmd node   || fail "node missing after install"
ok "prereqs present (git $(git --version | awk '{print $3}'), python $(python3 --version | awk '{print $2}'), node $(node -v))"

# --- clone / pull -----------------------------------------------------------
if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "Updating existing checkout at $INSTALL_DIR"
  git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
  log "Cloning $REPO_URL into $INSTALL_DIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi
ok "source ready at $INSTALL_DIR"

# --- backend ----------------------------------------------------------------
cd "$INSTALL_DIR/backend"
if [[ ! -d .venv ]]; then
  log "Creating Python venv"
  python3 -m venv .venv
fi
log "Installing backend dependencies"
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
deactivate
ok "backend deps installed"

if [[ ! -f .env ]]; then
  log "Seeding backend/.env"
  cp .env.example .env
  # generate a unique API key per install
  KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  # Use a python one-liner to avoid sed/portability issues
  python3 - <<PY
from pathlib import Path
p = Path('.env')
text = p.read_text()
text = text.replace('EG4_API_KEY=local-dev-key-change-me', f'EG4_API_KEY=$KEY')
text = text.replace('EG4_API_KEY=', f'EG4_API_KEY=$KEY')  # if blank line
p.write_text(text)
PY
  ok "generated unique API key (see backend/.env)"
fi

# --- frontend ---------------------------------------------------------------
cd "$INSTALL_DIR/frontend"
log "Installing frontend dependencies (npm install)"
npm install --silent --no-progress
log "Building frontend bundle"
npm run build --silent
ok "frontend built"

# --- launcher ---------------------------------------------------------------
cd "$INSTALL_DIR"
chmod +x start.sh stop.sh status.sh 2>/dev/null || true

LAUNCHER="$HOME/.local/bin/solarsage"
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# SolarSage launcher
exec "$INSTALL_DIR/solarsage.sh" "\$@"
EOF
chmod +x "$LAUNCHER"

if ! echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/.local/bin"; then
  warn "$HOME/.local/bin is not on your PATH"
  warn 'Add this to your ~/.zshrc or ~/.bashrc:'
  warn '    export PATH="$HOME/.local/bin:$PATH"'
fi
ok "launcher installed at $LAUNCHER"

# --- done -------------------------------------------------------------------
log "Starting SolarSage"
"$INSTALL_DIR/start.sh"

cat <<EOF

${GREEN}SolarSage is installed and running.${RESET}

  UI         http://127.0.0.1:5173
  API docs   http://127.0.0.1:8000/docs
  Source     $INSTALL_DIR
  API key    $(grep ^EG4_API_KEY "$INSTALL_DIR/backend/.env" | cut -d= -f2)

Sign in via the UI with your monitor.eg4electronics.com credentials, leave
"Remember me" checked, and you're done.

Common commands:
  solarsage start | stop | status | logs   (launcher on PATH)
  $INSTALL_DIR/start.sh | stop.sh | status.sh

Docs:
  $INSTALL_DIR/docs/ARCHITECTURE.md
  $INSTALL_DIR/docs/INSTALLATION.md
EOF
