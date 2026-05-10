<p align="center">
  <img src="solar_sage.png" alt="SolarSage" width="220" />
</p>

<h1 align="center">SolarSage</h1>
<p align="center"><em>Monitor · Predict · Optimize</em></p>

<p align="center">
  Local, vendor-neutral, weather-aware solar monitoring + forecasting.
  Talks to EG4, SolarEdge, (and soon Q.Cells), stores everything in SQLite,
  overlays an Open-Meteo-driven AC + production forecast, recommends
  smart-load windows, and exposes the whole thing as a REST + MCP surface
  any LLM can query.
</p>

---

## One-liner install

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/geekychris/solarsage/main/install.sh | bash
```

**Windows (PowerShell)**

```powershell
iwr -useb https://raw.githubusercontent.com/geekychris/solarsage/main/install.ps1 | iex
```

Then open <http://127.0.0.1:5173> and sign in with your monitoring-portal
credentials.

See [`docs/INSTALLATION.md`](docs/INSTALLATION.md) for manual install and
troubleshooting; [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how it
works inside.

## What it does

| | |
|---|---|
| **Live tiles** | Solar PV (per-string), load (main + EPS), battery SoC/V/A, grid in/out, EPS output, today/lifetime kWh. Auto-detects field names across firmware revisions. |
| **History & charts** | Range view (1d/3d/7d/14d/31d/90d + drag-to-zoom + brush), per-day chart, raw-data inspector, GitHub-style calendar heatmap. |
| **Forecasts** | Today's expected production headroom, tomorrow's hourly PV/AC/load/surplus, battery completion ETA, max-producible-now envelope. |
| **Smart load scheduler** | Given enabled appliances (water pump, washer, dishwasher, EV charger, …) recommends the best windows in the next 48h based on real surplus forecast. |
| **Multi-site, multi-vendor** | EG4 Monitor, SolarEdge (official API), Q.Cells (stub). Each site is its own location, lat/lon, capacity. |
| **AC model** | Cooling-degree regression fit from joint Open-Meteo + load history. Improves automatically as days accumulate. |
| **String health** | Flags strings producing under 60% of the strongest — catches shading, soiling, or panel issues early. |
| **Performance trend** | Actual daily kWh vs irradiance-expected. Catches gradual degradation that day-to-day variation hides. |
| **Anomaly alerts** | Background watcher fires on low SoC, daylight-but-no-PV, weak strings. Persisted, acknowledge-able. |
| **REST API** | Every panel is also a queryable endpoint. `/docs` is auto-OpenAPI. |
| **MCP server** | Same surface as native Claude / LLM tools — *"how much did I export last week?"* becomes a real tool call. |

## How it works

A FastAPI backend talks to the solar portals on your behalf, polls every
60 seconds, stores numeric fields into SQLite, and overlays forecast +
analytics on top. A small React (Vite) frontend renders it all. Everything
runs on `127.0.0.1` — no cloud component.

```mermaid
graph LR
  user([You]) --> ui[React UI]
  llm([Claude / MCP]) --> mcp[MCP server]
  ui --> api[FastAPI]
  mcp --> api
  api --> db[(SQLite)]
  api <--> eg4[EG4 Monitor]
  api <--> se[SolarEdge]
  api <--> om[Open-Meteo]
```

Read the full architecture doc: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Why a "local" app

* Your credentials never leave your machine — they sit in
  `backend/credentials.json` mode 0600.
* No telemetry, no analytics, no signup.
* You own the SQLite file. Years of high-resolution telemetry, queryable with
  plain SQL or via the REST/MCP API.
* If a portal changes, you can fix it. The whole codebase is ~3000 lines.

## Status / roadmap

| Feature | Status |
|---|---|
| EG4 live + history + backfill | ✅ shipping |
| Open-Meteo weather forecast + AC model | ✅ shipping |
| Multi-site data model + adapter pattern | ✅ shipping |
| SolarEdge adapter | ✅ shipping (paste API key in UI) |
| Q.Cells adapter | 🟡 stub — tell us your portal |
| Smart load scheduler | ✅ shipping |
| Anomaly alerts | ✅ shipping |
| Calendar heatmap, string health, perf trend | ✅ shipping |
| Mobile-responsive | ✅ shipping |
| CSV export | ✅ shipping |
| MCP server | ✅ shipping |
| Native notifications (browser, email) | 🟡 planned — backend rules already fire |
| Compare-days overlay | 🟡 planned |
| Cost-savings tracker w/ tariff input | 🟡 planned |

## License & contributing

MIT. Contributions welcome — adapter PRs for additional vendors are
especially valued. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#5-multi-site-adapter-pattern)
for the contract; a new vendor is usually 80–120 lines.

## Acknowledgements

* [`eg4-inverter-api`](https://pypi.org/project/eg4-inverter-api/) by
  Garreth Jeremiah — the EG4 live-data client we wrap.
* [`joyfulhouse/pylxpweb`](https://github.com/joyfulhouse/pylxpweb) — the
  reverse-engineered EG4 chart-endpoint catalog.
* [Open-Meteo](https://open-meteo.com/) — free, keyless weather + solar
  irradiance forecasts. Generous to a fault.
