# Rotation mode (fullscreen screensaver)

Turn a wall-mounted screen or spare tablet into a rotating dashboard
that walks through a chosen set of widgets full-screen, one at a time,
with per-widget dwell times.

Typical use: a fire-tablet in the kitchen showing Solar vitals every
other slot, then AQI, weather, tide table, HOA activities in the gaps.

## Quick start

1. Local tab → **Lists** → **Rotation (screensaver)** card.
2. Sequence starts with a sensible default (Solar every-other slot,
   then AQI / weather / tides / HOA rotating in the alternate slots).
3. Add / remove / reorder steps as you like. Same widget can appear
   multiple times — that's how you weight visibility.
4. Set per-step dwell in seconds (default = 20 s).
5. Click **▶ Launch fullscreen**.

## Keyboard + touch controls

| input | effect |
|---|---|
| Esc | Exit rotation |
| Space | Pause / resume |
| ← / → | Previous / next step |
| Click / tap header | Exit rotation |
| Double-tap content | Exit rotation |

Auto-advance runs on a wall clock, not a scroll — no matter what the
UI is doing, at the end of the dwell the next step swaps in.

## URL entry

Open rotation directly with `?view=rotation`:

```
https://pi-sf.hitorro.com/?view=rotation
```

Once loaded the query param is removed from history so a normal
back-navigation returns to the dashboard.

Add to a wall display's home screen and it launches straight into
rotation mode.

## How the sequence works

The config lives in the SQLite `widget_config` table under the special
id `_rotation`. Shape:

```json
{
  "enabled": true,
  "default_dwell_seconds": 20,
  "sequence": [
    {"widget_id": "solar_vitals", "dwell_seconds": 25},
    {"widget_id": "aqi",          "dwell_seconds": 15},
    {"widget_id": "solar_vitals", "dwell_seconds": 25},
    {"widget_id": "weather",      "dwell_seconds": 15},
    …
  ]
}
```

Steps are ordered. When the player reaches the end it loops back to
the start indefinitely.

## REST API

| Endpoint | Description |
|---|---|
| `GET /api/rotation` | Fetch current + default config |
| `PUT /api/rotation` | Replace the config (validates that each step has a widget_id) |

## What can go in the rotation

Widgets that read well as a big glance display — mostly the passive
ones. The config UI filters out the CRUD editors (contacts, shopping,
todo, border log, subscriptions) since they need keyboard input to be
useful.

Add any widget by editing the sequence in the JSON via
`PUT /api/rotation` if you want to override.

## Solar vitals widget

Purpose-built for the rotation. Shows:

* Current battery SoC (big number + progress bar)
* Live solar production
* Live house load
* Net charge/discharge rate
* Time to full or time to empty at current rate — with target clock
  time
* "Start conserving after X" projection when discharging past a
  configured SoC threshold (default 30%)

You can also drop it into the desktop grid — it lives on the Solar
sub-tab at position 3 by default.

## Tips

* **Weight what you want to see** — Solar vitals every other slot
  (`solar_vitals, X, solar_vitals, Y, solar_vitals, Z, …`) is the
  canonical layout for a solar-focused display.
* **Vary dwell times** — informational widgets like AQI can flash by
  in 10 s; a tide chart benefits from 25-30 s.
* **Test with the desktop preview** — before pushing to a wall
  display, hit ▶ Launch on your laptop, use `←` `→` to walk through,
  spot anything hard to read from across the room.
* **Combine with subscriptions** — TTS/Telegram alerts fire regardless
  of what's on screen, so you can rotate for glances and let the
  reminder scheduler shout about anything urgent.
