# Writing a widget

A widget is a self-describing dashboard tile with three parts:

1. **Metadata** — id, name, description, refresh cadence, JSON-schema
   hints for its data + config.
2. **Backend `fetch(config)`** — an async function that returns a
   JSON-serializable dict. Runs on a background loop every
   `refresh_seconds`.
3. **Frontend renderer** — a React component that receives the fetched
   data and draws it.

The registry, cache (SQLite), REST endpoints (`/api/widgets/*`), MCP
introspection tools, and background refresher are all provided — you
just write the two files and register the widget in one line.

## Backend

Create `backend/app/widgets/my_widget.py`:

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import aiohttp
from .base import Widget


class TrafficWidget(Widget):
    id = "traffic"                              # stable, used in /api/widgets/<id>
    kind = "traffic"                            # frontend renderer key
    name = "Traffic"                            # display name
    description = (
        "Live traffic conditions on the commute. Source: HERE Traffic API."
    )
    refresh_seconds = 5 * 60                    # backend fetch cadence
    default_tab = "Travel"                      # sub-tab under Local
    default_position = 25                       # ordering within the tab

    config_schema = {
        "type": "object",
        "properties": {
            "route_from": {"type": "string"},
            "route_to":   {"type": "string"},
        },
    }
    default_config = {
        "route_from": "31.025,-114.838",
        "route_to":   "32.667,-115.499",
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                "https://traffic.example/v1/route",
                params={"from": config["route_from"], "to": config["route_to"]},
                timeout=15,
            ) as r:
                r.raise_for_status()
                payload = await r.json()
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "duration_min": payload.get("duration") / 60,
            "distance_km":  payload.get("distance") / 1000,
        }
```

Then in `backend/app/main.py`, add the import + register:

```python
from .widgets.my_widget import TrafficWidget
# … in _register_builtin_widgets:
TrafficWidget(),
```

That's it. Restart the backend and `GET /api/widgets/traffic` works. The
MCP `list_widgets` / `widget_meta` / `widget_data` tools will find it
automatically.

## Frontend

Create `frontend/src/components/widgets/TrafficWidget.jsx`:

```jsx
import React from "react";

export default function TrafficWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div>
      <div style={{ fontSize: 24, fontWeight: 700 }}>
        {Math.round(data.duration_min)} min
      </div>
      <div className="muted">{data.distance_km?.toFixed(1)} km</div>
    </div>
  );
}
```

Then in `frontend/src/components/LocalTab.jsx`:

```jsx
import TrafficWidget from "./widgets/TrafficWidget.jsx";

const RENDERERS = {
  // …existing entries…
  traffic: TrafficWidget,        // matches the widget's `kind` field
};
```

Hard-refresh the browser and the card appears in the Travel sub-tab.

## Sheets-backed widgets

If your widget stores a user-editable list (contacts, todos, whatever)
opt into Google Sheets sync by setting three class attributes:

```python
class ContactsWidget(Widget):
    id = "contacts"
    # ...
    sheets_tab = "Contacts"                                 # workbook tab name
    sheets_list_field = "contacts"                          # array field in config
    sheets_field_order = ["name", "phone", "email",         # row 1 header + column order
                          "location", "tags", "notes"]
```

When `SOLARSAGE_SHEET_ID` + `GOOGLE_APPLICATION_CREDENTIALS` env vars
are set:

* `fetch()` reads rows from the sheet into `config[sheets_list_field]`
  before your code runs.
* `PUT /api/widgets/<id>/config` writes the list back to the sheet.
* Missing tabs are auto-created with the header row.

When Sheets isn't configured, widgets fall back to SQLite
`widget_config` transparently — nothing breaks.

Your `fetch()` just does:

```python
async def fetch(self, config):
    return {"contacts": config.get("contacts") or []}
```

## Sub-widget metadata

Widgets expose:

* `data` — the payload your `fetch` returned. Freeform.
* `data_schema` — JSON-schema-ish hint for what fields to expect.
  Informational only, not validated. This is what LLMs see over MCP.
* `config` — current effective config (user-set values + defaults).
* `config_schema` — same for the config surface.
* `layout` — `{tab, position}`. Users override via the UI or PUT
  `/api/widgets/<id>/layout`.

If a widget needs a custom settings UI (the `contacts` widget renders
its own CRUD form) the frontend renderer just does the editing directly
via `api.putWidgetConfig(id, {...cur.config, contacts: [...]})`. The
generic settings modal is a fallback for scalar config.

## Synthesizer widgets

Widgets can read other widgets' cached state — see
`backend/app/widgets/outdoor_fishing.py` (reads tides + sun_moon +
marine) and `backend/app/widgets/trip_planner.py` (reads drive_time +
border + weather + holidays). They use the same `WidgetStore` the
refresher uses:

```python
from .store import WidgetStore
import os

async def fetch(self, config):
    store = WidgetStore(os.getenv("EG4_DB_PATH", "./eg4_history.db"))
    tides = (await store.get_state("tides")).data
    # … synthesize
```

No network fetch of your own; you're just repackaging existing data.

## Catalog

Auto-generated from each widget class's metadata by
`tools/build_catalog.py`. Run it after adding a new widget:

```
python3 tools/build_catalog.py > /tmp/catalog.md
```

Then paste the table below.

| id | name | tab | refresh | description |
| -- | ---- | --- | ------- | ----------- |
| `aqi` | Air quality | Safety | 1 h | Current air quality (US AQI, PM2.5, PM10, ozone, dust) plus the next-24h peak. Source: Open-Meteo. |
| `quakes` | Earthquakes | Safety | 1 h | Recent felt earthquakes (M ≥ 2.5) within a configurable radius. Source: USGS. |
| `storms` | Tropical storms | Safety | 1 h | Active tropical cyclones (NHC). Filters to configured basins. |
| `uv_heat` | UV & heat stress | Safety | 1 h | Today's peak UV time + apparent-temperature danger window. Source: Open-Meteo. |
| `fishing_window` | Fishing windows | Outdoor | 1 h | Best fishing windows based on tide movement, dawn/dusk light, sea state. |
| `marine` | Marine forecast | Outdoor | 1 h | Sea conditions — wave height, wind, sea temperature. |
| `sea_temp` | Sea temperature | Outdoor | 1 h | Sea surface temperature current + 7-day forecast. |
| `sun_moon` | Sun & moon | Outdoor | 1 h | Sunrise / sunset / solar noon + moon phase. Local computation, no API. |
| `sunset` | Sunset countdown | Outdoor | 1 h | Live-ticking minutes to sunset + civil dusk with 'golden 20' highlight. |
| `tides` | Tide tables | Outdoor | 1 h | High/low tide predictions from worldtides.info. |
| `weather` | Weather | Outdoor | 1 h | Current conditions + 7-day forecast. Source: Open-Meteo. |
| `whale_season` | Whale watching | Outdoor | 1 h | Sea of Cortez whale-watching season indicator. |
| `border` | Border wait times | Travel | 1 h | US-Mexico border crossing wait times (CBP). |
| `costco_fuel` | Fuel prices | Travel | 1 h | Real CA retail avg from EIA + live per-station Pemex prices from CRE gov feed + manual Costco. |
| `currency` | MXN/USD | Travel | 1 h | Daily USD/MXN from Frankfurter (ECB), 14-day series. |
| `drive_time` | Drive times | Travel | 1 h | Driving distance / time between points (OSRM). |
| `holidays` | Mexican holidays | Travel | 1 h | Federal public holidays. |
| `return_countdown` | Days until return | Travel | 1 h | Countdown to your next drive back north. |
| `trip_planner` | Trip planner | Travel | 1 h | Daily 'go-score' for a US run combining drive time + border wait + weather. |
| `acpv_overlay` | AC vs PV overlay | Solar | 15 m | Today's PV + smart_ac consumption on one axis. EG4 history + HA. |
| `climate_chart` | Room climate history | Solar | 20 m | Temp + humidity 24 h / 7 d chart. Shares sensor list with `solar_vitals`. |
| `consumption_yoy` | Consumption YoY | Solar | 1 h | Today's load vs. same-day-last-year from EG4 history. |
| `precool` | Pre-cool advisor | Solar | 1 h | Suggests pre-cool window based on apparent-temperature peak. |
| `property_mode` | Property mode | Solar | 1 h | Occupied / Vacant / Arriving — other widgets can read this to relax alerts. |
| `solar_excess` | Excess-energy planner | Solar | 1 h | Today's solar surplus + suggested loads for the midday window. |
| `solar_vitals` | Solar vitals | Solar | 1 m | SoC, PV per-string, live load, projected time-to-full/empty, per-AC chip row, temp/humidity per room, per-AC override UI. |
| `when_to_run` | When to run | Solar | 1 h | Best contiguous window today/tomorrow for each configurable high-load appliance. |
| `baja_news` | Baja news | Community | 1 h | Regional headlines. |
| `baja_races` | Baja races | Community | 1 h | SCORE International off-road schedule. |
| `hoa` | El Dorado Ranch activities | Community | 1 h | Weekly PDF-scraped HOA activities. |
| `hoa_newsletter` | HOA newsletter | Community | 1 h | Latest HOA newsletter PDF. |
| `news` | News | Community | 1 h | Configurable RSS/Atom feeds. |
| `property_tax` | Property tax (predial) | Community | 1 h | San Felipe predial countdown. |
| `reservations` | Reservations | Community | 1 h | Upcoming bookings from iCal URLs. |
| `spanish` | Spanish practice | Community | 1 h | Phrase of the day + practice speak button. |
| `border_log` | Border crossing log | Lists | 1 h | Log of border crossings. |
| `contacts` | Contacts | Lists | 1 h | Address book. |
| `quicklinks` | Quick links | Lists | 1 h | Bookmarks. Ships with an "Apps" group for smart_ac and Home Assistant. |
| `shopping_list` | Shopping list | Lists | 1 h | Items to buy in the US on next border run. |
| `todo` | Todo | Lists | 1 h | General-purpose task list. |
| `water_tank` | Water tank | Local | 5 m | Cistern % full, gallons, days-remaining projection, tiered low-level announcements. HA depth sensor. |

**Recent additions** (July 2026): `sunset`, `water_tank`, `when_to_run`,
`acpv_overlay`, `climate_chart`. **Recent changes to existing widgets**:
`solar_vitals` grew a per-AC override UI, per-room temp/humidity chip
row, and pie-chart hover; `costco_fuel` picked up real live Pemex data.

## Widget health

Every widget's `fetch` result is stored in the `widget_state` table with
`fetched_at` and `error` fields. If `fetch` raises, the exception is
logged, `error` is populated, and the loop keeps running — the widget
serves stale data until the next successful fetch. The UI shows the
error string inline.
