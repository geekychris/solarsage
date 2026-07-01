# Alerts & notifications

SolarSage can take action when a widget's data crosses a threshold —
speak through the local Pi speaker, ping you on Telegram via Home
Assistant, or anything else you plug in as a new channel.

Two moving parts:

* **Notification channels** — where a message goes (TTS, HA notify
  services, log).
* **Subscription rules** — when to send it (condition on any widget
  field, cooldown-limited, edge-triggered).

## Channels

Every rule action carries a `type`:

| type | what it does | env config needed |
|---|---|---|
| `tts` | POST to the local `tts_speaker.py` service at `http://localhost:5006/say`; plays through the Pi's HDMI/audio-out via `ffplay`. | none — `TTS_URL` overrides |
| `telegram` | POST to a Home Assistant service. Despite the name, it can target **any** HA notify service (persistent_notification, alexa_media_*, telegram_bot.send_message, mobile_app_*, …). | `HA_URL`, `HA_TOKEN`, `NOTIFY_TELEGRAM_SERVICE`, `NOTIFY_TELEGRAM_TARGET` |
| `log` | Writes to the backend log only. Great for testing rules without spamming Telegram. | none |

Adding a new channel is one function in `backend/app/notify.py` +
one entry in the `CHANNELS` dict. See `_tts` / `_telegram` for the
shape.

### Telegram via Home Assistant

HA is the router — SolarSage doesn't know about your bot token or
chat IDs. Two setup steps:

1. **Get a long-lived HA access token** — HA UI → your profile
   (bottom-left) → Security → **Long-lived access tokens** → Create
   Token → name it "SolarSage". Copy it (shown once).

2. **Add to `backend/.env`**:
   ```
   HA_URL=http://homeassistant.local:8123
   HA_TOKEN=<paste from step 1>
   NOTIFY_TELEGRAM_SERVICE=telegram_bot.send_message
   NOTIFY_TELEGRAM_TARGET=123456789
   ```

   `NOTIFY_TELEGRAM_TARGET` is your Telegram chat_id (send `/start`
   to `@userinfobot` in Telegram to find it). Comma-separate for
   multiple. Numeric strings are coerced to int for the HA payload.

3. **Restart**: `scripts/deploy.sh` or `sudo systemctl restart
   solarsage-backend.service`.

**Smoke test** (no rule required):

```bash
curl -sSk -X POST https://pi-sf.hitorro.com/api/notify/test \
  -H 'X-API-Key: <your-key>' -H 'Content-Type: application/json' \
  -d '{"type":"telegram","text":"hello","title":"SolarSage test"}'
```

Returns `{"ok":true, "detail":"HA telegram_bot.send_message ok"}` when
HA accepts. Check your Telegram for the message.

Other HA notify services work too — just point
`NOTIFY_TELEGRAM_SERVICE` at any of them. Examples:

* `notify.persistent_notification` — shows in the HA notification tray
* `notify.alexa_media_everywhere` — broadcasts to every Echo device
* `notify.mobile_app_your_iphone` — HA Companion push
* `notify.telegram` — the classic YAML-configured notify (if you have one)

## Subscription rules

A rule watches one field on one widget and fires actions when a
condition crosses false → true.

### Anatomy

```json
{
  "id": "…",
  "widget_id": "aqi",
  "name": "AQI unhealthy",
  "condition": {
    "path":  "current.us_aqi",
    "op":    ">",
    "value": 100
  },
  "message":  "AQI is {current.us_aqi} ({current.category})",
  "actions": [
    {"type": "tts"},
    {"type": "telegram", "title": "SolarSage · AQI"}
  ],
  "cooldown_minutes": 60,
  "enabled": true
}
```

### Fields

| field | meaning |
|---|---|
| `widget_id` | Which widget the condition reads from. |
| `condition.path` | Dotted path into the widget's `data`. Supports `[n]` indices (e.g. `ports[0].pov.standard.delay_minutes`). |
| `condition.op` | `>`, `>=`, `<`, `<=`, `==`, `!=`, `contains`, `not_contains`, `changed`. |
| `condition.value` | RHS of the comparison. Auto-typed on save (numeric strings → int/float, `true`/`false` → bool). |
| `message` | Template rendered against the widget's data. `{a.b.c}` gets substituted with the path lookup. |
| `actions` | List of action dicts (see channel table above). |
| `cooldown_minutes` | Minimum gap between fires. 0 = no cooldown. |
| `enabled` | Off rules are stored but never evaluated. |

### Semantics

* Evaluated **after every widget refresh** — no separate timer.
* **Edge-triggered**: fires when the condition goes false → true.
  Doesn't re-fire while still true; re-arms on false again.
* **Cooldown** applies on top of the edge-trigger: a rule can't fire
  more than once per cooldown window even if it re-arms and matches.
* **Failure isolation**: a broken rule (invalid path, missing target)
  logs a warning and moves on; other rules still fire.

### REST API

| method | path | purpose |
|---|---|---|
| GET | `/api/subscriptions` | list all rules |
| POST | `/api/subscriptions` | create or update (send `id` to update) |
| DELETE | `/api/subscriptions/{id}` | delete |
| POST | `/api/subscriptions/{id}/test` | fire the rule's actions **now** (bypass condition + cooldown). Renders `message` against current widget data. |
| POST | `/api/notify/test` | fire one raw action for testing. Body is an action dict: `{"type":"tts","text":"..."}` |

### UI

Local tab → **Lists** sub-tab → **Alert rules** card:

* **+ Add rule** — inline form. Picking a widget pre-fills a
  suggested `condition.path`, `op`, `value`, and `message` template
  (until you type over them).
* **🔔 Test** — fires the rule's actions immediately. Green banner
  when all channels succeed, yellow if partial, red if the request
  itself failed.
* **✎ Edit** / **✕ Delete** — standard.

### Recipes

**Tropical storm warning**
```json
{
  "widget_id": "storms",
  "name": "Tropical storm active",
  "condition": {"path": "active_count", "op": ">", "value": 0},
  "message": "{active_count} active storm(s) in {basins_watched}",
  "actions": [{"type": "tts"}, {"type": "telegram", "title": "Storm alert"}],
  "cooldown_minutes": 360
}
```

**Property tax two weeks out**
```json
{
  "widget_id": "property_tax",
  "name": "Predial due soon",
  "condition": {"path": "days_until_due", "op": "<=", "value": 14},
  "message": "Property tax due in {days_until_due} days ({due_this_year})",
  "actions": [{"type": "telegram", "title": "Predial reminder"}],
  "cooldown_minutes": 4320
}
```

**Solar surplus for pool pump**
```json
{
  "widget_id": "solar_excess",
  "name": "Lots of surplus today",
  "condition": {"path": "today.estimated_excess_kwh", "op": ">=", "value": 20},
  "message": "{today.estimated_excess_kwh} kWh surplus — run the pool pump",
  "actions": [{"type": "tts"}],
  "cooldown_minutes": 720
}
```
