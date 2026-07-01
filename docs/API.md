# REST + MCP reference

Every dashboard panel is also a queryable endpoint. Home Assistant,
your phone, another LLM — anything that speaks HTTP can consume this.
The full spec is auto-generated at:

* **Swagger UI**: `https://<host>/docs`
* **Raw OpenAPI JSON**: `https://<host>/openapi.json`

The endpoints below are the highlights. Authentication is either:

* `Authorization: Bearer <token>` from `POST /api/login`, or
* `X-API-Key: <key>` set via `EG4_API_KEY` in `backend/.env`. Read-only
  endpoints accept the key; endpoints that talk to EG4 need a live
  session.

## Solar (existing)

| Endpoint | Description |
|---|---|
| `POST /api/login` | Get a session token |
| `GET /api/inverters` | List discovered EG4 inverters |
| `GET /api/snapshot?serial=<sn>` | Real-time telemetry |
| `GET /api/energy?serial=<sn>` | Today + lifetime totals |
| `GET /api/history?serial=<sn>&field=<f>&range_minutes=<n>` | Field-level time series |
| `GET /api/range?serial=<sn>&days=<n>&fields=ppv,soc,...` | Multi-series range chart |
| `GET /api/daychart?serial=<sn>&date=YYYY-MM-DD` | Per-day chart |
| `GET /api/heatmap?serial=<sn>&days=365` | Calendar heatmap |
| `GET /api/summary?serial=<sn>&days=30` | Best/worst days |
| `GET /api/aggregate?serial=<sn>&field=<f>&group_by=day&fn=sum` | Any bucket |
| `GET /api/forecast/solar_today?serial=<sn>` | Today's expected production |
| `GET /api/forecast/tomorrow?serial=<sn>` | Hourly PV/AC/load/surplus |
| `GET /api/forecast/excess?serial=<sn>` | Headroom envelope |
| `GET /api/forecast/battery_completion?serial=<sn>` | Charge-to-100 ETA |
| `GET /api/schedule?serial=<sn>&site_id=<s>` | Smart load windows |
| `GET /api/weather?days=7` | Open-Meteo cache |
| `GET /api/alerts?site_id=<s>` | Anomaly alerts |
| `POST /api/sync?serial=<sn>&days=30` | Bulk historical sync |
| `GET /api/export.csv?serial=<sn>&field=<f>&start=<ms>&end=<ms>&api_key=<k>` | CSV export |

## Widgets

| Endpoint | Description |
|---|---|
| `GET /api/widgets` | List every widget with meta + cached data |
| `GET /api/widgets/<id>` | One widget's full payload |
| `GET /api/widgets/<id>/meta` | Just the schema + description (LLM introspection) |
| `GET /api/widgets/<id>/data` | Just the cached data |
| `GET /api/widgets/<id>/config` | Effective + default config |
| `PUT /api/widgets/<id>/config` | Update config (writes to Sheets when applicable) |
| `PUT /api/widgets/<id>/layout` | Move to another tab or reorder |
| `POST /api/widgets/<id>/refresh` | Force immediate refresh |

## Events + reminders

| Endpoint | Description |
|---|---|
| `GET /api/events` | All events (optional window) |
| `GET /api/events/today` | Today's events |
| `GET /api/events/upcoming?days=2` | Grouped by day |
| `POST /api/events` | Create a manual event |
| `PUT /api/events/<id>` | Update / snooze |
| `DELETE /api/events/<id>` | Delete |
| `PUT /api/events/<id>/reminders` | Set reminder schedule |
| `POST /api/events/<id>/say` | Test TTS for this event |
| `POST /api/events/ingest_hoa` | Force HOA PDF re-scan |

## News archive

| Endpoint | Description |
|---|---|
| `GET /api/news/history?widget_id=<id>&limit=100&translate_to=en` | Full archive with cached translations |
| `POST /api/news/translate` | Batch-translate item IDs; caches to `translations` table |

## Notifications & subscriptions

| Endpoint | Description |
|---|---|
| `POST /api/notify/test` | Fire one raw action for testing. Body: `{"type":"telegram","text":"hi","title":"optional"}`. Returns `{ok, detail}`. |
| `GET /api/subscriptions` | List all rules with last-fired metadata |
| `POST /api/subscriptions` | Create / update. Send `id` to update. Rule shape in [NOTIFICATIONS.md](NOTIFICATIONS.md). |
| `DELETE /api/subscriptions/{id}` | Delete |
| `POST /api/subscriptions/{id}/test` | Fire the rule's actions **now** — bypass condition + cooldown. Renders `message` template against the widget's current data. |

## Translations

| Endpoint | Description |
|---|---|
| `POST /api/translations` | Translate + log (uses MyMemory) |
| `GET /api/translations?limit=50` | Recent phrase book |
| `POST /api/translations/<id>/star` | Toggle star |
| `DELETE /api/translations/<id>` | Delete |

## TTS

| Endpoint | Description |
|---|---|
| `POST /api/tts/say {"text": "..."}` | Speak arbitrary text through the local TTS service |

## MCP

The MCP server in `mcp_server/server.py` wraps the same REST surface as
structured tool calls. Register it with Claude Code:

```
mkdir -p .mcp
cat > .mcp/solarsage.json <<EOF
{
  "command": "python",
  "args": ["-m", "mcp_server.server"],
  "env": {
    "SOLARSAGE_BASE": "http://127.0.0.1:8000",
    "SOLARSAGE_API_KEY": "<your key>"
  }
}
EOF
```

Available tools:

* `list_sites`, `list_inverters`, `aggregate`, `summary`, `best_day`,
  `range_data`, `forecast_tomorrow`, `forecast_excess`,
  `battery_completion`, `schedule`, `string_health`, `performance`,
  `weather`, `list_alerts`
* `list_widgets`, `widget_meta`, `widget_data` — widget introspection
* `list_events_today`, `list_events` — HOA + manual events

## Home-automation recipes

**Home Assistant template sensor for today's events:**

```yaml
sensor:
  - platform: rest
    name: SolarSage Today
    resource: http://pi-sf.hitorro.com:8000/api/events/today
    headers:
      X-API-Key: !secret solarsage_api_key
    value_template: "{{ value_json.events | length }}"
    json_attributes:
      - events
    scan_interval: 300
```

**"Should I go north today?" from the trip planner:**

```yaml
sensor:
  - platform: rest
    name: SF Trip Planner
    resource: https://pi-sf.hitorro.com/api/widgets/trip_planner/data
    verify_ssl: false
    headers:
      X-API-Key: !secret solarsage_api_key
    value_template: "{{ value_json.data.total_trip_min_today }}"
```

**Push border wait to a dashboard:**

```yaml
sensor:
  - platform: rest
    name: Calexico West Wait
    resource: https://pi-sf.hitorro.com/api/widgets/border/data
    verify_ssl: false
    headers:
      X-API-Key: !secret solarsage_api_key
    value_template: >
      {{ value_json.data.ports
         | selectattr("port_number","eq","250302") | list
         | map(attribute="pov.standard.delay_minutes") | first }}
```
