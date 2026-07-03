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
| **Local widgets** | 35+ self-describing dashboard tiles beyond solar — tides, border wait times, marine forecast, HOA activities, tropical storms, quakes, Mexican holidays, drive-time planner, currency, air quality, and more. Auto-organized into sub-tabs (Safety / Outdoor / Travel / Solar / Community / Lists). |
| **Events + TTS reminders** | Auto-extracts events from the El Dorado Ranch HOA weekly PDF, schedules configurable reminders, speaks them through a local TTS service ("Movie Night starts in 60 minutes"). |
| **Google Sheets sync** | User-editable lists (contacts, shopping, todo, border crossings, bookmarks) live in a Google Sheets workbook — edit from any device, dashboard picks it up. |
| **Persistent news archive + translation** | RSS feed items stored in SQLite; headlines translated on-demand via MyMemory and cached forever. |
| **Threshold subscriptions** | Declarative "if X then TTS + Telegram" rules per widget. Edge-triggered, cooldown-limited, per-rule test button. |
| **MQTT + Home Assistant discovery** | Every widget publishes to your MQTT broker with an HA discovery config — sensors appear in Home Assistant automatically. |
| **Mobile / touch view** | Single-column stream + bottom tab bar + 48-px targets. Auto-detects touch devices; add to iOS home screen for a PWA-lite. |
| **Fullscreen rotation mode** | "Screensaver" cycler that walks through selected widgets full-screen with per-step dwell times. Includes a purpose-built **Solar vitals** widget (SoC, PV, load, time-to-full/empty, cut-back projection). |

## Documentation

* [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — install + configuration
* [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Pi setup, systemd, apache, backups
* [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit together
* [`docs/WIDGETS.md`](docs/WIDGETS.md) — writing your own widget (backend + frontend renderer)
* [`docs/SHEETS.md`](docs/SHEETS.md) — Google Sheets integration setup
* [`docs/NOTIFICATIONS.md`](docs/NOTIFICATIONS.md) — subscriptions, channels, HA notify wiring
* [`docs/MQTT.md`](docs/MQTT.md) — MQTT publish + HA MQTT discovery
* [`docs/MOBILE.md`](docs/MOBILE.md) — mobile / touch layout + add-to-home-screen
* [`docs/ROTATION.md`](docs/ROTATION.md) — fullscreen rotation player + Solar vitals widget
* [`docs/API.md`](docs/API.md) — REST + MCP reference (auto-generated OpenAPI at `/docs`)

## UI walkthrough

Annotated tour of every panel. Screenshots are live captures from a real EG4
system running in San Felipe, Mexico.

### Automated dashboard tour

The images below are captured programmatically from a live SolarSage. To
refresh them after UI changes:

```bash
export EG4_USERNAME=... EG4_PASSWORD=...
export SOLARSAGE_URL=https://pi-sf.hitorro.com   # or your own host
./scripts/capture-screenshots.sh
git add docs/screenshots && git commit -m "chore: refresh screenshots"
```

The script (`tools/capture-screenshots.mjs`) uses Playwright + headless
Chromium, logs in with the credentials above, walks every tab + settings
modal + rotation view, and writes 17 PNGs into `docs/screenshots/`. Manifest
lives at `docs/screenshots/manifest.json`.

<p align="center">
  <img src="docs/screenshots/01-dashboard-solar.png" alt="Solar tab" width="900" />
</p>

**Solar tab** — Solar Vitals (SoC, per-string PV, live load, per-AC override, per-room temperature/humidity), Room Climate History chart, When-to-Run recommender, Peak Load recorder, Forecast Accuracy tracker, AC vs PV overlay, Consumption YoY.

<p align="center">
  <img src="docs/screenshots/02-dashboard-outdoor.png" alt="Outdoor tab" width="900" />
</p>

**Outdoor tab** — weather + 7-day forecast, tide tables (with real Pemex prices via CRE gov feed on the Travel tab), sunset countdown with golden-20 highlight, Sky Tonight (locally-computed planet positions), Meteor Showers with announcement window.

<p align="center">
  <img src="docs/screenshots/03-dashboard-safety.png" alt="Safety tab" width="900" />
</p>

**Safety tab** — earthquakes (USGS, magnitude + radius filters), tropical storms (NHC basin filter), UV & heat stress, air quality (US AQI + PM2.5/PM10/ozone).

<p align="center">
  <img src="docs/screenshots/04-dashboard-travel.png" alt="Travel tab" width="900" />
</p>

**Travel tab** — trip planner with border wait + weather score, US-Mx border wait times, fuel prices (real EIA California avg + live per-station Pemex from CRE gov feed with reverse-geocoded addresses + manual Costco entry with staleness meter), MXN/USD, driving distance + time.

<p align="center">
  <img src="docs/screenshots/05-dashboard-community.png" alt="Community tab" width="900" />
</p>

**Community tab** — HOA activities (weekly PDF auto-scraped), Today's events with per-event reminders, RSS/Atom news, Baja races, property tax countdown, Spanish practice phrase of the day.

<p align="center">
  <img src="docs/screenshots/06-widget-solar-vitals.png" alt="Solar Vitals widget" width="720" />
</p>

**Solar Vitals** (dense, defaults to 2× width) — big-number SoC, live per-string PV production, load breakdown pie chart with hover attribution, per-appliance chips, per-AC override popover ("Turn OFF for 30m / 1h / 2h / 4h — Release to smart_ac"), per-room temperature + humidity chip row, projected time-to-full / time-to-empty with a "start conserving" cut-back warning.

<p align="center">
  <img src="docs/screenshots/07-widget-climate-chart.png" alt="Room Climate History" width="720" />
</p>

**Room Climate History** — multi-line temperature + humidity over configurable 24h / 3d / 7d windows, with a hover crosshair that lifts the matching sensor read-out. Shares the sensor list with Solar Vitals.

<p align="center">
  <img src="docs/screenshots/08-widget-water-tank.png" alt="Water Tank" width="480" />
</p>

**Water Tank** — reads a Home Assistant ultrasonic depth sensor; renders % full, gallons remaining (from configurable gallons-per-foot geometry), days-remaining projection from the 7-day trend, and tiered warning bar at 50/25/10%. Warnings fire via the announcements framework (TTS + Telegram, respecting quiet hours).

<p align="center">
  <img src="docs/screenshots/09-widget-peak-load.png" alt="Peak Load" width="720" />
</p>

**Peak Load** — rolling 30-day max simultaneous load, plus today's peak, plus a per-day bar chart. Red bars mark days that got close to the inverter limit.

<p align="center">
  <img src="docs/screenshots/10-widget-acpv-overlay.png" alt="AC vs PV overlay" width="720" />
</p>

**AC vs PV Overlay** — 24 h of PV production overlaid with smart_ac consumption (integrated per-room via HA history + calibration). Hover crosshair shows values at any minute. Diagnoses whether smart_ac tracked the sun today.

<p align="center">
  <img src="docs/screenshots/11-widget-sky-tonight.png" alt="Sky Tonight" width="480" />
</p>

**Sky Tonight** — naked-eye planets tonight (Mercury / Venus / Mars / Jupiter / Saturn) with rise, peak, set times and peak altitude; moon phase + illumination. Local VSOP-style math, no external API.

<p align="center">
  <img src="docs/screenshots/12-settings-system.png" alt="Settings — System" width="820" />
</p>

**Settings → System** — Leaflet + OpenStreetMap location picker (click or drag the marker), coordinates + timezone, system peak kW / battery kWh / inverter max charge, history retention, editable tab labels (rename or merge tabs — e.g. relabel "Solar" and "Local" both as "House"), external services (Home Assistant URL + token, TTS URL, Telegram service + target, WorldTides + EIA API keys — all revealable with an eye toggle).

<p align="center">
  <img src="docs/screenshots/13-settings-notifications.png" alt="Settings — Notifications" width="820" />
</p>

**Settings → Notifications** — Global quiet-hours envelope (per-channel muting during a nightly window). Per-source enable + channel + threshold config for tides, HOA events, storms, quakes, battery-charged, excessive-discharge, water-low, meteor showers. Per-row "Test" button fires a synthetic announcement to verify TTS + Telegram end-to-end. Recent announcements log at the bottom with a "Replay last N minutes" action.

<p align="center">
  <img src="docs/screenshots/14-settings-ha-integrations.png" alt="Settings — HA Integrations" width="820" />
</p>

**Settings → HA Integrations** — one card per widget that reads Home Assistant. Each row shows the current entity ID, a live-value read-out, and an autocomplete-backed entity picker. Save validates the new entity exists in HA before writing. The Solar Vitals card also has a bespoke Room Sensors editor for adding / renaming / removing temperature+humidity pairs.

<p align="center">
  <img src="docs/screenshots/15-settings-rotation.png" alt="Settings — Rotation" width="820" />
</p>

**Settings → Rotation** — configure the full-screen "screensaver" widget rotation with per-step dwell time. Same widget can appear multiple times to weight visibility. Launch from `?view=rotation`; Esc exits, Space pauses, ← → step.

<p align="center">
  <img src="docs/screenshots/16-rotation-mode.png" alt="Rotation mode" width="900" />
</p>

**Rotation mode** — full-screen kiosk view, auto-advancing through the configured widget sequence. Ideal for a wall-mounted Raspberry Pi displaying the house state.

<p align="center">
  <img src="docs/screenshots/17-mobile-dashboard.png" alt="Mobile view" width="360" />
</p>

**Mobile viewport** — same widgets, same data, 1-column grid on narrow screens (grid-column spans collapse under 700 px).

### Every widget, close-up

Each widget captured individually so you can see what data lives where. Grouped by tab.

<details><summary><b>Safety</b> (4 widgets)</summary>

| Widget | Screenshot |
|---|---|
| **Air quality** — US AQI + PM2.5/PM10/ozone/dust + 24h peak. Source: Open-Meteo. | <img src="docs/screenshots/20-widget-aqi.png" alt="Air quality" width="500" /> |
| **Earthquakes** — recent felt quakes (M ≥ 2.5) within a configurable radius. Source: USGS. | <img src="docs/screenshots/21-widget-quakes.png" alt="Earthquakes" width="500" /> |
| **Tropical storms** — active NHC cyclones, filtered to configured basins (default EP). | <img src="docs/screenshots/22-widget-storms.png" alt="Storms" width="500" /> |
| **UV & heat** — peak UV time + apparent-temperature danger window today and tomorrow. | <img src="docs/screenshots/23-widget-uv_heat.png" alt="UV & heat" width="500" /> |

</details>

<details><summary><b>Outdoor</b> (10 widgets)</summary>

| Widget | Screenshot |
|---|---|
| **Weather** — current + 7-day forecast (Open-Meteo). | <img src="docs/screenshots/24-widget-weather.png" width="500" /> |
| **Tide tables** — highs/lows from tidetime.org scraper (no API key). | <img src="docs/screenshots/25-widget-tides.png" width="500" /> |
| **Marine forecast** — wave height, wind, sea temperature + best-window hint. | <img src="docs/screenshots/26-widget-marine.png" width="500" /> |
| **Sea temperature** — current + 7-day forecast + swim/fishing context. | <img src="docs/screenshots/27-widget-sea_temp.png" width="500" /> |
| **Sun & moon** — sunrise/sunset/solar noon + moon phase, local math. | <img src="docs/screenshots/28-widget-sun_moon.png" width="500" /> |
| **Sunset countdown** — live-ticking minutes to sunset, 'golden 20' highlight. | <img src="docs/screenshots/29-widget-sunset.png" width="500" /> |
| **Fishing windows** — best hours from tide movement + dawn/dusk + sea state. | <img src="docs/screenshots/30-widget-fishing_window.png" width="500" /> |
| **Whale watching** — Sea of Cortez fin/blue/gray whale season indicator. | <img src="docs/screenshots/31-widget-whale_season.png" width="500" /> |
| **Meteor showers** — next shower peak + ZHR; announces days ahead. | <img src="docs/screenshots/32-widget-meteor_showers.png" width="500" /> |
| **Bird migration** — species moving through the Baja Pacific Flyway this month. | <img src="docs/screenshots/33-widget-bird_migration.png" width="500" /> |

</details>

<details><summary><b>Travel</b> (7 widgets)</summary>

| Widget | Screenshot |
|---|---|
| **Border wait times** — CBP data for US-Mexico crossings. | <img src="docs/screenshots/34-widget-border.png" width="500" /> |
| **Fuel prices** — real CA retail avg (EIA) + live per-station Pemex (CRE gov feed) + manual Costco with staleness. | <img src="docs/screenshots/35-widget-costco_fuel.png" width="500" /> |
| **Days until return** — countdown to your next drive back north. | <img src="docs/screenshots/36-widget-return_countdown.png" width="500" /> |
| **MXN/USD** — daily rate from Frankfurter (ECB) with 14-day trailing series. | <img src="docs/screenshots/37-widget-currency.png" width="500" /> |
| **Drive times** — OSRM distance + duration between configured points. | <img src="docs/screenshots/38-widget-drive_time.png" width="500" /> |
| **Mexican holidays** — federal public holidays with countdown to the next. | <img src="docs/screenshots/39-widget-holidays.png" width="500" /> |
| **Trip planner** — daily 'go-score' combining drive time + border wait + weather. | <img src="docs/screenshots/40-widget-trip_planner.png" width="500" /> |

</details>

<details><summary><b>Solar</b> (6 additional widgets — Solar Vitals, Climate History, Peak Load, AC vs PV, Sky Tonight above)</summary>

| Widget | Screenshot |
|---|---|
| **Consumption YoY** — today's load vs same-day-last-year from EG4 history. | <img src="docs/screenshots/41-widget-consumption_yoy.png" width="500" /> |
| **Forecast accuracy** — 30 days of forecast vs actual PV; tune `peak_kw` when biased. | <img src="docs/screenshots/42-widget-forecast_accuracy.png" width="500" /> |
| **Property mode** — Occupied / Vacant / Arriving; other widgets adjust off this. | <img src="docs/screenshots/43-widget-property_mode.png" width="500" /> |
| **Excess-energy planner** — expected surplus + suggested loads for midday. | <img src="docs/screenshots/44-widget-solar_excess.png" width="500" /> |
| **Pre-cool advisor** — window based on apparent-temperature peak and SoC. | <img src="docs/screenshots/45-widget-precool.png" width="500" /> |
| **When to run** — best contiguous window today/tomorrow per configured high-load appliance. | <img src="docs/screenshots/46-widget-when_to_run.png" width="500" /> |

</details>

<details><summary><b>Community</b> (8 widgets)</summary>

| Widget | Screenshot |
|---|---|
| **Baja news** — configurable regional RSS/Atom outlets. | <img src="docs/screenshots/47-widget-baja_news.png" width="500" /> |
| **Baja races** — SCORE International off-road schedule with ★ for SF-involved events. | <img src="docs/screenshots/48-widget-baja_races.png" width="500" /> |
| **HOA newsletter** — latest El Dorado Ranch weekly PDF, auto-scraped. | <img src="docs/screenshots/49-widget-hoa_newsletter.png" width="500" /> |
| **El Dorado Ranch activities** — auto-parsed weekly activities PDF. | <img src="docs/screenshots/50-widget-hoa.png" width="500" /> |
| **News** — configurable RSS/Atom feeds (defaults: NHC + USGS). | <img src="docs/screenshots/51-widget-news.png" width="500" /> |
| **Property tax (predial)** — San Felipe predial countdown with paid-this-year toggle. | <img src="docs/screenshots/52-widget-property_tax.png" width="500" /> |
| **Reservations** — upcoming bookings from configured iCal URLs. | <img src="docs/screenshots/53-widget-reservations.png" width="500" /> |
| **Spanish practice** — daily phrase, speak button (via pi5 TTS), and dictation quiz. | <img src="docs/screenshots/54-widget-spanish.png" width="500" /> |

</details>

<details><summary><b>Lists</b> (5 widgets)</summary>

| Widget | Screenshot |
|---|---|
| **Border crossing log** — every crossing (direction, port, actual vs quoted wait, notes). | <img src="docs/screenshots/55-widget-border_log.png" width="500" /> |
| **Contacts** — address book (name/phone/email/location) shared with the phone. | <img src="docs/screenshots/56-widget-contacts.png" width="500" /> |
| **Quick links** — grouped bookmarks. Ships an 'Apps' group with smart_ac + HA. | <img src="docs/screenshots/57-widget-quicklinks.png" width="500" /> |
| **Shopping list** — items to buy in the US on your next border run. | <img src="docs/screenshots/58-widget-shopping_list.png" width="500" /> |
| **Todo** — priority (1..5), optional due date, done flag, notes. Syncs to Sheets when enabled. | <img src="docs/screenshots/59-widget-todo.png" width="500" /> |

</details>

---

### Panel-by-panel walkthrough (original, pre-July 2026)

### Login

<img src="docs/screenshots/login.annotated.png" alt="Login screen" width="720" />

| # | What | Notes |
|---|---|---|
| **1** | Logo + tagline | App brand and the "Monitor · Predict · Optimize" promise |
| **2** | Username | Your `monitor.eg4electronics.com` login |
| **3** | Password | Stored locally only — never sent anywhere except EG4 |
| **4** | **Remember me** | Saves credentials to `backend/credentials.json` (mode 0600) so the backend auto-logs in on every restart. The UI re-acquires its session on reload without you typing anything. |
| **5** | Sign in | One-shot — checks credentials against EG4 + (if remember-me) writes the local file |
| **6** | Security disclosure | App is local-only. Don't expose port 8000 publicly. |

### Dashboard

<img src="docs/screenshots/dashboard_top.annotated.png" alt="Dashboard top" width="900" />

| # | What | Notes |
|---|---|---|
| **1** | **SolarSage** brand | Click to refresh the page if anything looks stale |
| **2** | Sync controls | `30d` ↔ window dropdown · **Sync** button → calls `/api/sync` to pull N days of historical data from EG4 in one click |
| **3** | Last update | When the UI last received fresh snapshot data (auto-refresh every 15s) |
| **4** | **Settings · Sign out · Forget** | Settings opens the location/capacity modal. "Forget" deletes saved credentials. |
| **5** | Sites panel | Multi-site/multi-vendor. Each row is a configured system (EG4, SolarEdge, Q.Cells). `+ Add site` opens the inline form. |
| **6** | Inverters | Auto-discovered from the selected site. Click to switch. |
| **7** | Inverter header | Plant name · serial · firmware. Anchors the live-data tiles. |
| **8** | **Solar PV** tile | Real-time PV in watts. The `ppv1+ppv2+ppv3` sub-label tells you *which* fields were summed — many EG4 firmwares only populate per-string powers, so we sum them. |
| **9** | **Load** tile | Live consumption. Sub-label shows the source field; for EPS-wired homes it pulls from `pEpsL1N+pEpsL2N (EPS)` because `consumptionPower` is zero. |
| **10** | Grid + battery tiles | To Grid / From Grid / Battery charge / discharge / EPS output / SoC / voltage / current. All field names auto-detected. |
| **11** | "Today" tiles | Today's energy totals (kWh): solar, load, charge, discharge, export, import — straight from EG4's daily counters. |
| **12** | **Smart load scheduler** | Headline feature — best 48h windows to run discretionary loads. See below. |

### Smart load scheduler

<img src="docs/screenshots/scheduler.annotated.png" alt="Smart load scheduler" width="900" />

For every enabled, deferrable appliance, the scheduler scans your weather-aware
48h surplus forecast for a window where *every hour* clears the appliance's
watts — not just the average. Ranked by sustained surplus.

| # | What | Notes |
|---|---|---|
| **1** | Section title | Updates every 5 minutes |
| **2** | Appliance name | Pulled from the Appliances panel below |
| **3** | Power × runtime | What the appliance needs to run a full cycle |
| **4** | **Recommended start** | Local time. Click to copy to clipboard (in a future revision) |
| **5** | Average surplus | How much spare solar there'll be during the window — anything above the appliance's watts means zero grid/battery draw |

Real numbers from the screenshot: tomorrow ~13:00 has 7,768 W of sustained surplus,
which comfortably covers a water heater (4,500 W), washer, dishwasher, and an AC
boost — they all get the same window because the surplus is plenty.

### Weather & AC forecast

<img src="docs/screenshots/weather.annotated.png" alt="Weather forecast" width="900" />

| # | What | Notes |
|---|---|---|
| **1** | Panel title | Open-Meteo source + your lat/lon |
| **2** | **Outside now** | Real temperature + apparent temp from Open-Meteo current observation |
| **3** | **AC model** | Fitted from your joint load + Open-Meteo history. `78 W/°F above 70°F, R²=0.43, 15d`: every °F above 70 outside adds ~78W to your AC load. R² rises as data accumulates. |
| **4** | **Tomorrow PV** | Predicted kWh from forecasted GHI × your system's calibration |
| **5** | **Tomorrow AC load** | The AC model applied to tomorrow's hourly temps. The "76% of total load" sub-label tells you what fraction of tomorrow's expected load is AC vs base. |
| **6** | 7-day strip | Daily high/low/UV from Open-Meteo. The 104°F day stands out — that's a heat wave coming. |
| **7** | 48-hour chart | Green area = predicted PV · red line = predicted total load (incl. AC) · orange dashed = AC contribution alone · gold line on right axis = outside °F. The AC line tracks temperature almost 1:1 — that's the cooling-degree model working. |

### Production headroom & excess

<img src="docs/screenshots/excess.annotated.png" alt="Production headroom" width="900" />

| # | What | Notes |
|---|---|---|
| **1** | **Max producible now** | Best PV your system has actually produced at this time-of-day in the last 14 days, capped by clear-sky theoretical |
| **2** | **Expected load now** | Historical avg load at this hour (captures AC time-of-day pattern) |
| **3** | **Excess available now** | The headroom — how many watts you could deploy a discretionary load into without grid/battery |
| **4** | **Utilization right now** | Today's actual PV ÷ expected max. If this is 60%, you're probably under cloud or shade. |
| **5** | **Peak excess later** | When and how much surplus is coming. Use to time discretionary loads manually. |
| **6** | **Total excess today** | All the headroom you have through end-of-day, in kWh |
| **7** | Remaining excess | Same as 6, but only counting from now → sunset |
| **8** | Chart | Clear-sky envelope (dashed orange) · expected-max (dashed bold green) · excess (blue filled area) · expected load (red) · today's actual PV (solid bright green) · today's actual load (orange). Dashed vertical line marks "now". |

### Range view

<img src="docs/screenshots/range.annotated.png" alt="Range chart with drag-to-zoom" width="900" />

| # | What | Notes |
|---|---|---|
| **1** | Title | Shows current span + auto-bucket size + point count |
| **2** | **Presets** | `1d` `3d` `7d` `14d` `31d` `90d` — anchored to "now" |
| **3** | End-date picker | Snap the window's end to a specific date; current span preserved |
| **4** | Reset zoom | Returns to the last preset after a custom drag-zoom |
| **5** | Channel toggles | Show/hide individual series (Solar / Load main / Load EPS / battery charge / discharge / grid / SoC). Defaults to "useful for most installs". |
| **6** | **Drag-to-zoom** | Click + drag horizontally → the highlighted region becomes the new window. Re-queries at finer bucket resolution automatically. |
| **7** | Brush bar | Scrub a sub-range within the loaded data — no network call, just changes the visible window |

The bucket size auto-snaps: 1d → 5min, 7d → 1h, 90d → 6h. Always lands around
~500 points per series.

### Appliances configuration

<img src="docs/screenshots/appliances.annotated.png" alt="Appliances panel" width="900" />

| # | What | Notes |
|---|---|---|
| **1** | Panel title | Per-site list |
| **2** | **Enable toggle** | Disabled rows are skipped by the scheduler |
| **3** | Name | Editable inline |
| **4** | Watts | Typical draw while running |
| **5** | Run min | How long one cycle lasts |
| **6** | Defer? | If unchecked (e.g. computer workstations), the scheduler won't suggest a window — these run when they run |
| **7** | Pref window | Optional `start_hour → end_hour` to limit recommendations (e.g. dishwasher 11→15) |
| **8** | + add new row | Custom appliances on top of the seeded catalog |

Default seeded catalog matches a typical North American install with pool pump
and electric dryer **disabled by default** (you mentioned you don't have those).

### Other panels (unannotated)

**Sites panel** — manage multi-vendor, multi-location systems. Each site is its
own lat/lon/capacity/credentials.

<img src="docs/screenshots/sites_panel.png" alt="Sites panel" width="320" />

**Heatmap** — GitHub-contributions-style yearly grid. One cell per day, shaded
by daily kWh. Toggle `30d/90d/365d` window.

<img src="docs/screenshots/heatmap.png" alt="Production heatmap" width="900" />

**System health** — per-string PV balance + actual-vs-irradiance-expected
performance trend. The warning banner fires when a string runs below 30% of
the strongest one. (In the screenshot, **ppv3 = 0% consistently** — that's a
real issue worth investigating: unused channel, panel/fuse fault, or shading.)

<img src="docs/screenshots/health.png" alt="System health" width="900" />

**Alerts** — anomaly watcher records low-SoC, daylight-but-no-PV, and weak-string
events. Each alert is dismissable; rules deduplicate to one fire per hour per
rule per site.

<img src="docs/screenshots/alerts.png" alt="Alerts panel" width="900" />

**Settings modal** — system-level config: lat/lon (DST-aware tz), peak DC kW,
battery capacity, max charge rate, historical-curve window size. All forecasts
use these.

<img src="docs/screenshots/settings_modal.png" alt="Settings modal" width="720" />

**Battery charge forecast** — projected SoC trajectory and 100% ETA based on
the historical solar curve + measured charge rate.

<img src="docs/screenshots/battery_forecast.png" alt="Battery forecast" width="900" />

**Raw data inspector** — every field EG4 returned in the last snapshot,
split by category. Use this when a tile shows `—` to find the actual field
name on your firmware.

<img src="docs/screenshots/raw_data.png" alt="Raw data" width="900" />

---

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
