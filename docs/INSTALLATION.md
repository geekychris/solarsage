# Installing SolarSage

SolarSage runs locally on your machine — backend on `127.0.0.1:8000`, UI on
`127.0.0.1:5173`. No cloud component, no external accounts beyond your
solar-portal credentials.

## One-liner install

> **Read what you're piping before piping** — every responsible reader of a
> `curl | bash` thinks this. The script's source is at
> [`install.sh`](../install.sh) (macOS/Linux) and
> [`install.ps1`](../install.ps1) (Windows). Skim them.

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/geekychris/solarsage/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
iwr -useb https://raw.githubusercontent.com/geekychris/solarsage/main/install.ps1 | iex
```

Both installers:

1. Check for `git`, Python 3.9+, Node 18+; install via Homebrew or winget
   if missing (with your consent — they prompt before touching anything).
2. Clone the repo into `~/solarsage` (configurable).
3. Create the Python venv, install backend requirements.
4. Run `npm install` + `npm run build` for the frontend.
5. Seed `backend/.env` from `.env.example` with a generated `EG4_API_KEY`.
6. Drop launcher scripts on your PATH (`solarsage start`, `solarsage stop`,
   `solarsage status`, `solarsage logs`).
7. Print the URL to open and tell you to sign in.

Total time on a warm system: about 90 seconds.

## Manual install

If you'd rather see every step:

### 1. Prerequisites

| Tool | Version | macOS | Windows | Linux |
| --- | --- | --- | --- | --- |
| Python | ≥3.9 | `brew install python@3.11` | `winget install Python.Python.3.11` | distro package |
| Node | ≥18 | `brew install node` | `winget install OpenJS.NodeJS.LTS` | nvm / distro |
| Git | any | preinstalled | `winget install Git.Git` | distro package |

### 2. Clone

```bash
git clone https://github.com/geekychris/solarsage.git
cd solarsage
```

### 3. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# (edit .env if you want a different DB path / API key)
```

### 4. Frontend

```bash
cd ../frontend
npm install
npm run build                       # for the production bundle
# OR: npm run dev   (for hot-reload during development)
```

### 5. Start both servers

Two separate terminals:

```bash
# terminal 1 — backend
cd solarsage/backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 — frontend
cd solarsage/frontend
npm run dev
```

Or use the bundled launcher (created by the installer, or run manually):

```bash
./start.sh             # macOS/Linux
./start.ps1            # Windows
```

### 6. Open <http://127.0.0.1:5173> and sign in

Use your `monitor.eg4electronics.com` credentials. Check **Remember me** —
the backend will then auto-login on every restart and Claude / scripts can
reach the data through the API key (configured in `backend/.env`).

## Configuration

`backend/.env` is the only config you usually need to touch. Defaults:

```ini
EG4_DB_PATH=./eg4_history.db
EG4_BASE_URL=https://monitor.eg4electronics.com
EG4_POLL_INTERVAL=60
EG4_DISABLE_VERIFY_SSL=0           # set to 1 if your network intercepts TLS
EG4_API_KEY=                       # set to any random string; required for /api/*?api_key= and X-API-Key auth
EG4_USERNAME=                      # optional — alt to UI "remember me"
EG4_PASSWORD=
```

In the UI, hit **Settings** for lat/lon/tz, system peak kW, battery capacity,
and the historical-curve window. Multi-site config (additional EG4 sites,
SolarEdge sites, Q.Cells sites) lives in the **Sites** panel in the sidebar.

## Connecting a SolarEdge site

1. Log into <https://monitoring.solaredge.com>.
2. **Admin → Site Access → API Access → Enable API** (you might need to
   tick "I have read the terms" first).
3. Copy the **API key** and the **site ID** (the number in the URL after
   `/site/`).
4. In SolarSage: **Sites → Add site**, pick `SolarEdge`, paste both, save.

The backend will start polling that site in addition to your EG4 system.

## Connecting a Q.Cells site

Q.Cells panels are deployed with different monitoring stacks depending on the
hardware partner (Hyundai inverters → Q.OMMAND; many residential installs →
Enphase Enlighten; some EU bundles → Sungrow iSolarCloud). Open the **Sites →
Add site** form, choose `Q.Cells`, and write which portal you log into. We'll
plug in the right adapter — most are 80–120 lines of code each.

## MCP server (optional)

To let Claude or another MCP-capable LLM query your solar data with structured
tool calls instead of curl:

```bash
pip install "mcp[cli]" httpx
SOLARSAGE_BASE=http://127.0.0.1:8000 \
SOLARSAGE_API_KEY=<your key from .env> \
python -m mcp_server.server
```

See [`mcp_server/README.md`](../mcp_server/README.md) for Claude Code
registration.

## Reset / uninstall

```bash
# stop everything
solarsage stop

# wipe local state (config, history, credentials)
rm -f backend/eg4_history.db backend/credentials.json backend/.env

# remove the install
rm -rf ~/solarsage
```

Nothing was ever installed system-wide except (optionally) the prerequisites
listed at the top.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `TLS error reaching https://monitor.eg4electronics.com` | Set `EG4_DISABLE_VERIFY_SSL=1` in `backend/.env`. Common on networks with TLS-inspecting middleboxes. |
| Login works in browser but fails here | Open <http://127.0.0.1:8000/docs> → POST /api/diagnostic to see raw EG4 response, or POST /api/debug/eg4 with the path you want to probe. |
| "no SoC samples yet" in battery forecast | Wait a minute — the poller needs at least one cycle. Faster: click **Sync** in the top bar. |
| `npm run dev` says port 5173 in use | Either you have a stale Vite running (`lsof -ti :5173 \| xargs kill`) or change the port in `frontend/vite.config.js`. |
| AC model R² very low | Need more days of joint weather + load history. After 3-4 weeks of summer it sharpens dramatically. |
