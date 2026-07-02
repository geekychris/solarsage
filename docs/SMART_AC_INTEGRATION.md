# Integrating with the San Felipe smart_ac / Home Assistant API

**Purpose.** This file is a briefing prompt for a code assistant working
on SolarSage. It explains how SolarSage can consume live AC-related data
and (if desired) control the air-conditioners in the San Felipe house.
Copy this into your Claude Code session's context, or leave it on disk
for future sessions to discover.

## Sibling repo

Everything below is *implemented* in the homeassistant repo:

- **GitHub**: https://github.com/geekychris/homeassistant_work_sanfelipe
- **Local clone**: `~/code/claude_world/homeassistant`

This SolarSage repo (`github.com/geekychris/solarsage`) is the *consumer*.
When making changes that touch AC control, keep the two repos in sync —
if you add an entity or change semantics, update this doc *and* mention it
in the homeassistant repo's README (which links back here).

**What SolarSage now does with smart_ac** (as of 2026-07):

- Reads `sensor.smart_ac_calibration` + `input_boolean.ac_<room>` to render
  a live per-room chip row in the Solar Vitals widget with scaled watts.
- Exposes `POST /api/smart_ac/override` — a thin wrapper that flips
  `input_boolean.ac_<room>` **and** sets
  `input_datetime.ac_<room>_override_until` so the scheduler stops
  re-evaluating that room until the timer expires. Frontend surfaces this
  as a "Turn ON/OFF for {30m,1h,2h,4h}" popover under each AC chip, plus
  a "Release to smart_ac" button that clears the override.
- Does *not* touch `input_boolean.smart_ac_enabled`. That kill switch is
  user-only (per this doc's guidance).

---

## Background: what `smart_ac` is

The San Felipe house has six air conditioners driven by a scheduler
called `smart_ac` running on `pi-sf.hitorro.com`. It evaluates the
battery / solar / temperatures / time-of-day every 5 minutes and decides
which ACs should be ON. It publishes three Home Assistant sensor
entities that summarise everything a downstream service would want:

| Entity | What it holds |
|---|---|
| `sensor.smart_ac_status` | Latest decision — mode, target rooms, per-room reasons, live inputs (SoC, load, PV, indoor/outdoor temps) |
| `sensor.smart_ac_calibration` | Per-AC measured wattage (baseline / running / delta) |
| `sensor.smart_ac_retrospective` | Nightly aggregate — per-mode minutes, per-AC runtime, per-AC estimated energy + $ cost |

Control primitives are Home-Assistant-native input helpers:

- `input_boolean.ac_{master,guest,dining,living,office,kyle}` — one per AC. Flip via `input_boolean.turn_on/turn_off` service calls. A downstream automation bridges these to the physical ACs via Alexa routines.
- `input_datetime.ac_<room>_override_until` — one per AC. Any future value pins that room in its current state until that datetime. Past value or 1970-01-01 = no override.
- `input_boolean.smart_ac_enabled` — scheduler kill switch (`on` = scheduler runs, `off` = no automated action).

## The API

**Base URL:** `http://ha-sf.hitorro.com:8123` (LAN only from within the San Felipe network; use VPN or a reverse tunnel for external access).

**Auth:** every request needs `Authorization: Bearer <HA long-lived token>`. Create one in the HA UI (Profile → Security → Long-Lived Access Tokens) and store it as a secret (env var, secrets manager). **Never** commit it to git — the smart_ac repo's `.gitignore` excludes `token.txt`, `bot_token.txt`, `*.env`, `secrets.yaml`.

**Content type:** all requests and responses are `application/json`.

**Spec:** the authoritative machine-readable spec lives at:

- File in the smart_ac repo: `homeassistant/docs/openapi.yaml`
- GitHub raw URL: https://raw.githubusercontent.com/geekychris/homeassistant_work_sanfelipe/main/docs/openapi.yaml

It's OpenAPI 3.0.3. Feed it to `openapi-generator-cli`, `openapi-python-client`, `swagger-ui`, or any other tool that speaks OpenAPI. It covers **only** the smart_ac subset of Home Assistant's REST API. For anything else (history, logbook, other integrations), consult the full HA docs at https://developers.home-assistant.io/docs/api/rest/.

## What SolarSage should probably do

1. **Read** `sensor.smart_ac_status` on a cadence matching your dashboard refresh (recommended: no more than once per 30 s — HA state updates propagate in near-real-time but the scheduler only changes decisions every 5 min).
2. **Read** `sensor.smart_ac_calibration.attributes.results` on startup and whenever the value changes. This gives you accurate per-AC watts you can multiply by runtime to estimate consumption. Keys are room slugs (`master`, `guest`, `dining`, `living`, `office`, `kyle`); each value has `baseline_w`, `running_w`, `delta_w`, `note`.
3. **Read** `sensor.smart_ac_retrospective` once a day (or whenever `attributes.run_at` changes) for the daily summary. Contains per-room `runtime_min`, `draw_w`, and `costs.{room}.{kwh, usd, watts_used, watts_source}`.
4. **Show live AC state** by reading the six `input_boolean.ac_<room>` entities and correlating with `sensor.smart_ac_status.attributes.reasons` for the per-room explanation.

## What SolarSage should NOT do without explicit user confirmation

- **Do not** flip `input_boolean.ac_<room>` on the user's behalf just because you think it would save power. The scheduler already reasons about that. If you want SolarSage to make suggestions, surface them as "recommendations" and require a user click.
- **Do not** disable `input_boolean.smart_ac_enabled` from an automated flow — that's the kill switch. If you're going to do something unusual, the user should press the button, not you.
- **Do not** write to any `sensor.*` entity — those are outputs of upstream systems and setting them via the state API leaves them out of sync with their real source.

If a user explicitly asks SolarSage to control an AC, use these two patterns:

**Turn a room ON immediately (scheduler may re-evaluate in ≤5 min):**
```http
POST /api/services/input_boolean/turn_on
Authorization: Bearer <token>
Content-Type: application/json

{"entity_id": "input_boolean.ac_living"}
```

**Turn a room ON and pin it (scheduler won't touch it until 22:00):**
```http
POST /api/services/input_boolean/turn_on
{"entity_id": "input_boolean.ac_living"}

POST /api/services/input_datetime/set_datetime
{"entity_id": "input_datetime.ac_living_override_until",
 "datetime": "2026-07-01 22:00:00"}
```

**Clear an override:**
```http
POST /api/services/input_datetime/set_datetime
{"entity_id": "input_datetime.ac_living_override_until",
 "datetime": "1970-01-01 00:00:00"}
```

Manual flips (`turn_on/turn_off` alone, without a paired `set_datetime`) **do not auto-pin** the state — the scheduler will re-evaluate on its next 5-min tick. This is intentional (an earlier auto-pin heuristic was removed because it fought explicit overrides). If SolarSage wants a change to stick, always pair the flip with a `set_datetime` in the future.

## Room slugs

The six room slugs used everywhere: `master`, `guest`, `dining`, `living`, `office`, `kyle`. Anywhere you see `<room>` in a path or entity ID, substitute one of these.

## Sample: read calibration + present it

```python
import httpx, os

HA = "http://ha-sf.hitorro.com:8123"
TOKEN = os.environ["HA_TOKEN"]
HDR = {"Authorization": f"Bearer {TOKEN}"}

def per_ac_watts() -> dict[str, int]:
    r = httpx.get(f"{HA}/api/states/sensor.smart_ac_calibration", headers=HDR)
    r.raise_for_status()
    results = r.json()["attributes"]["results"]
    return {room: info["delta_w"] for room, info in results.items()
            if info.get("note") == "ok"}
```

## Sample: subscribe-style polling for live decisions

HA's WebSocket API supports true push subscriptions but is out of scope for the OpenAPI spec. If SolarSage prefers push, connect to `ws://ha-sf.hitorro.com:8123/api/websocket`, auth with the same bearer token, then subscribe to `state_changed` events filtered by entity. See https://developers.home-assistant.io/docs/api/websocket/ for the handshake. For most dashboards a 15–30 s polling loop on `/api/states/sensor.smart_ac_status` is simpler and Good Enough.

## Cost / energy math the retrospective already does

If you want to compute cost yourself instead of relying on the nightly retrospective:

- Get per-AC watts from `sensor.smart_ac_calibration.attributes.results[room].delta_w`. If the note isn't `ok`, use a default (~1000 W) and label the estimate as "default".
- Get runtime by summing minutes the corresponding `input_boolean.ac_<room>` was `on` over your window (query `/api/history/period/<from-iso>?filter_entity_id=input_boolean.ac_living`).
- Cost = `runtime_min / 60 * watts / 1000 * rate_usd_per_kwh`. The house uses `$0.30/kWh` as its opportunity cost (off-grid, no utility bill, valued against a hypothetical grid replacement).

The retrospective already does exactly this every night and publishes to `sensor.smart_ac_retrospective.attributes.costs`. Prefer that if a 24-h resolution is acceptable.

## Where to ask questions / look for detail

- Human-readable reference: `docs/SMART_AC.md` in the homeassistant repo (https://github.com/geekychris/homeassistant_work_sanfelipe/blob/main/docs/SMART_AC.md).
- Machine-readable spec: `docs/openapi.yaml` (same repo).
- Change history: `README.md` in that repo is the reverse-chronological journal.
- The smart_ac scheduler code is in `smart_ac/smart_ac.py` (decision logic), `smart_ac/calibrate.py` (calibration), `smart_ac/retrospective.py` (nightly analysis), `smart_ac/web.py` (LAN-only http://pi-sf.hitorro.com:5010 dashboard).
