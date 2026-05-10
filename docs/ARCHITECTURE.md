# SolarSage architecture

SolarSage is a small two-tier app — a FastAPI backend and a React frontend —
that talks to one or more solar-monitoring portals, stores everything in
SQLite, and overlays forecast / scheduling / health analytics on top. This
document explains the pieces and how data flows between them.

## 1. System overview

```mermaid
graph LR
  user([Browser]) -->|http :5173| ui[React UI<br/>Vite + Recharts]
  ui -->|REST :8000| api[FastAPI backend]
  llm([MCP-capable LLM]) -->|stdio| mcp[MCP server<br/>mcp_server/]
  mcp -->|REST| api

  api <-->|JSESSIONID| eg4[EG4 Monitor<br/>monitor.eg4electronics.com]
  api <-->|API key| se[SolarEdge<br/>monitoringapi.solaredge.com]
  api -.->|TBD| qc[Q.Cells portal]
  api <-->|GET| om[Open-Meteo<br/>api.open-meteo.com]

  api --> db[(SQLite<br/>eg4_history.db)]
  api --> creds[(credentials.json<br/>mode 0600)]

  subgraph host[Your machine — localhost-only]
    ui
    api
    mcp
    db
    creds
  end

  classDef external fill:#333,stroke:#999,color:#ddd;
  class eg4,se,qc,om external;
```

Everything except the four external services runs on your machine on
`127.0.0.1`. The backend listens only on loopback by default; nothing is
exposed to the LAN unless you intentionally change `--host`.

## 2. Repo layout

```
solarsage/
├── backend/
│   ├── app/
│   │   ├── main.py                FastAPI app, all endpoints, lifespan
│   │   ├── storage.py             SQLite schema + queries
│   │   ├── session_store.py       In-memory bearer/site session registry
│   │   ├── credentials.py         Local credentials.json read/write/clear
│   │   ├── adapters/              Vendor-agnostic monitoring portal clients
│   │   │   ├── base.py            SiteAdapter ABC + Inverter dataclass
│   │   │   ├── eg4.py             Wraps eg4-inverter-api
│   │   │   ├── solaredge.py       Official monitoringapi.solaredge.com
│   │   │   └── qcell.py           Stub (awaiting portal confirmation)
│   │   ├── eg4_history.py         EG4 chart endpoints (dayLine etc.)
│   │   ├── poller.py              Background snapshot loop
│   │   ├── alerts_watcher.py      Background anomaly engine
│   │   ├── forecast.py            Today/excess/battery-completion model
│   │   ├── ac_model.py            Cooling-degree regression for AC load
│   │   ├── solar.py               NOAA solar position + clear-sky envelope
│   │   ├── weather.py             Open-Meteo client
│   │   ├── scheduler.py           Smart appliance window picker
│   │   ├── appliances_catalog.py  Default appliance catalog
│   │   └── schemas.py             Pydantic request/response models
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                       (gitignored — your local config)
├── frontend/
│   ├── src/
│   │   ├── App.jsx                Routing + boot auth recovery
│   │   ├── api.js                 Typed-ish REST wrapper
│   │   ├── components/            One file per panel (~15 components)
│   │   └── styles.css
│   ├── public/solarsage.png
│   ├── vite.config.js
│   └── package.json
├── mcp_server/
│   ├── server.py                  FastMCP wrapper around the REST API
│   └── README.md
├── docs/                          You're here
├── install.sh / install.ps1       One-shot installers
├── start.sh / start.ps1           Run both servers
└── solar_sage.png                 App logo
```

## 3. Boot + auth flow

```mermaid
sequenceDiagram
  participant U as User browser
  participant F as React UI
  participant B as FastAPI
  participant C as credentials.json
  participant E as EG4 portal

  F->>B: GET /api/auth/status
  B->>C: load()
  C-->>B: { username, password } or None
  B-->>F: { credentials_persisted, active_sessions }

  alt no saved creds
    U->>F: type username/pw, ✓ Remember me
    F->>B: POST /api/login {username, pw, remember=true}
    B->>E: POST /WManage/api/login (form-encoded)
    E-->>B: 200 + JSESSIONID cookie
    B->>C: save(username, pw)  (mode 0600)
    B-->>F: { token, inverter_count, remembered=true }
  else saved creds
    F->>B: POST /api/auth/use_saved (no auth)
    B-->>F: { token } from auto-login session
  end

  Note over F: token stored in localStorage<br/>used as Bearer for further calls
```

On startup the backend's lifespan kicks off an `_auto_login_loop` task that
reads saved credentials and keeps a session + poller alive forever, re-auth'ing
on failure. The UI never holds your password; it's only in
`backend/credentials.json` (chmod 600, gitignored).

## 4. Live polling + historical backfill

```mermaid
graph TB
  subgraph live[Live polling — every 60s]
    poll[poller task] -->|runtime/energy/battery| eg4api[EG4 API]
    eg4api --> flatten[flatten numeric fields]
    flatten --> sqlite[(samples table)]
  end

  subgraph backfill[On-demand backfill]
    user[Sync button or /api/sync] -->|N days| dayloop[for each local date]
    dayloop -->|dayLine attr=ppv1/2/3, pCharge,<br/>pDisCharge, soc, peps, …| chartapi[EG4 chart API]
    chartapi --> merge[merge points by timestamp,<br/>synthesize ppv = Σppv-n]
    merge -->|UPSERT idempotent| sqlite
  end

  subgraph schema[samples table — tall/skinny]
    sqlite -->|"(site_id, serial, ts, category, field, value)"| reads
  end
```

The schema is **tall/skinny** — every numeric field becomes its own row. This
lets us add new metrics from new firmware revisions without migrations, and
makes per-field aggregation trivial (`SELECT AVG(value) ... WHERE field=?`).

Backfill uses EG4's per-attribute `dayLine` chart endpoint because the
"all-channels" `dayMultiLineParallel` endpoint returns empty on SNA-US
firmware. We issue ~30 parallel calls per day and merge by timestamp. The
chart endpoint's `time` string is preferred over `year`/`month`/`day`/`hour`
because EG4's month field is **Java zero-indexed** (May = 4).

## 5. Multi-site adapter pattern

```mermaid
classDiagram
  class SiteAdapter {
    +site_id: str
    +credentials: dict
    +config: dict
    +login() async
    +close() async
    +list_inverters() Inverter[]
    +runtime(serial) async dict
    +energy(serial) async dict
    +battery(serial) async dict
    +fetch_day(serial, date, tz) async list
  }

  class EG4Adapter {
    -client: EG4InverterAPI
    +login() async
    +runtime, energy, battery, fetch_day
  }

  class SolarEdgeAdapter {
    -api_key: str
    -se_site_id: str
    +login() async  // validates via /inventory
    +runtime via currentPowerFlow
    +fetch_day via powerDetails
  }

  class QCellAdapter {
    +login() async  // NotImplementedError
  }

  SiteAdapter <|-- EG4Adapter
  SiteAdapter <|-- SolarEdgeAdapter
  SiteAdapter <|-- QCellAdapter
```

A `sites` row carries vendor + credentials JSON + config JSON. The factory in
`adapters/__init__.py` dispatches by vendor. The rest of the app talks only
to the ABC.

## 6. Forecast pipeline

```mermaid
graph LR
  subgraph inputs
    history[(SQLite history)]
    om[Open-Meteo<br/>forecast + archive]
    sun[Solar position math<br/>solar.py]
    settings[Site settings<br/>lat/lon/peak_kw/cap]
  end

  history -->|bucket avg by hour-of-day| acfit[Fit AC model<br/>ac_model.py]
  om -->|archive temps| acfit
  acfit -->|threshold + slope W/°F| accmodel{AC model}

  history -->|peak observed PV| pvcal[PV calibration]
  om -->|forecast GHI| pvcal
  pvcal -->|W per W/m²| pvscale

  om -->|hourly forecast<br/>temp, GHI, cloud| combine[Per-hour rows]
  settings --> combine
  accmodel --> combine
  pvscale --> combine
  sun --> combine

  combine --> tomorrow["/api/forecast/tomorrow<br/>hourly: PV, base, AC, load, surplus"]
  combine --> excess["/api/forecast/excess<br/>per-bucket max producible<br/>vs expected load"]
  combine --> sched["/api/schedule<br/>best windows per appliance"]
```

The AC model is intentionally simple:

`load(hour, °F)  =  base(hour)  +  slope_W_per_°F · max(0, °F − threshold)`

We fit `threshold` and `slope` by grid-search + OLS on residuals against
Open-Meteo's *historical* hourly temperature for the same time range as the
stored load samples. With 15 days of joint data this typically lands around
R² 0.4–0.5; it sharpens as more days accumulate.

PV calibration is even simpler: ratio of *observed peak PV* to *forecast peak
GHI*, expressed as **watts of system output per watt-per-m² of irradiance**.
Real number from a 15kW EG4 system at low-desert latitudes: ~9 W per W/m².

## 7. Smart load scheduler

```mermaid
graph LR
  tomorrow[Tomorrow forecast<br/>hourly surplus] --> sched
  appl[(appliances table<br/>enabled + deferrable)] --> sched
  sched{For each appliance:<br/>slide N-hour window<br/>until min surplus ≥ watts}
  sched --> recs[Ranked recommendations<br/>by average surplus]
```

`schedule_appliances()` only suggests windows where *every* hour in the
window clears the appliance's draw — not just the average. That prevents
"the dishwasher tries to start during a cloud passage" cases.

Appliances flagged `can_defer=false` (e.g. computer workstations) are
skipped — they run when they run, not on a schedule. Preferred-hour windows
(`preferred_start_hour`, `preferred_end_hour`) narrow further if set.

## 8. Anomaly alerts

```mermaid
sequenceDiagram
  participant W as alerts_watcher (every 60s)
  participant H as History (SQLite)
  participant S as solar.py
  participant A as alerts table
  participant UI as AlertsPanel

  loop every minute
    W->>H: list_sites()
    loop each site/serial
      W->>H: latest(soc)
      alt soc < 25
        W->>A: record_alert(low_soc)
      end
      W->>S: sun_position(lat, lon, now)
      alt elevation > 25° AND latest(ppv) < 200W
        W->>A: record_alert(daylight_no_pv)
      end
      W->>H: latest(ppv1, ppv2, ppv3, …)
      alt weakest < 60% of strongest AND strongest ≥ 500W
        W->>A: record_alert(weak_string)
      end
    end
  end
  UI->>A: poll /api/alerts every 60s
  UI-->>UI: render badges + acknowledge button
```

Each rule has **1-hour suppression** so a sustained problem fires once per
hour, not every minute.

## 9. REST surface

The full surface is auto-documented at <http://127.0.0.1:8000/docs>. Highlights:

| Category | Endpoints |
| --- | --- |
| Auth | `POST /api/login`, `POST /api/logout`, `GET /api/auth/status`, `POST /api/auth/use_saved` |
| Live | `GET /api/runtime`, `/api/energy`, `/api/battery`, `/api/snapshot` |
| History | `GET /api/history`, `/api/range`, `/api/daychart`, `/api/coverage`, `/api/metrics` |
| Analytics | `GET /api/aggregate`, `/api/summary`, `/api/best_day`, `/api/heatmap`, `/api/string_health`, `/api/performance` |
| Sync | `POST /api/sync`, `/api/backfill`, `GET /api/diagnostic`, `POST /api/debug/eg4` |
| Forecast | `GET /api/forecast/{tomorrow,excess,solar_today,battery_completion,max_production}`, `/api/weather`, `/api/schedule` |
| Multi-site | `GET/POST /api/sites`, `DELETE /api/sites/{id}`, `GET/POST /api/appliances`, `DELETE /api/appliances/{id}` |
| Alerts | `GET /api/alerts`, `POST /api/alerts/{id}/ack` |
| Settings | `GET/PUT /api/settings` |
| Export | `GET /api/export.csv` |

**Two auth modes**: `Authorization: Bearer <token>` (UI flow) **or**
`X-API-Key: <env-configured key>` (scripts, MCP, curl). Endpoints that only
read SQLite accept either; endpoints that talk to the EG4 portal require a
live session.

## 10. Where data lives

| Thing | Where | Notes |
| --- | --- | --- |
| All time-series samples | `backend/eg4_history.db` (SQLite) | One file. Back this up. |
| Sites + appliances + alerts | same SQLite | |
| Active EG4/SolarEdge session | in-process memory | Re-established on backend restart from saved creds |
| Saved credentials | `backend/credentials.json` | mode 0600, gitignored |
| App config (lat/lon/peak kW) | `settings` table in SQLite | Editable via UI |
| Local env overrides | `backend/.env` | TLS bypass, DB path, etc. — gitignored |
| Frontend assets | served by Vite dev server (`:5173`) or built into `frontend/dist/` | |

A clean reset is: stop both servers, delete `backend/eg4_history.db` and
`backend/credentials.json`, and start over.
