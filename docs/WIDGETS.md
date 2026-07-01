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

## Widget health

Every widget's `fetch` result is stored in the `widget_state` table with
`fetched_at` and `error` fields. If `fetch` raises, the exception is
logged, `error` is populated, and the loop keeps running — the widget
serves stale data until the next successful fetch. The UI shows the
error string inline.
