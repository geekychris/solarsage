# MQTT publish + Home Assistant discovery

SolarSage can publish every widget's state to an MQTT broker and
register a matching Home Assistant discovery config so widgets appear
as HA entities automatically — no YAML template sensors needed.

## What gets published

| topic | payload | purpose |
|---|---|---|
| `solarsage/widgets/<id>/state` (retain) | `{fetched_at, error, widget_id, widget_kind}` | State topic HA reads for the entity's `state` (via `value_template: {{ value_json.fetched_at }}`) |
| `solarsage/widgets/<id>/attributes` (retain) | `{data, meta, published_at}` | All widget fields, exposed as entity attributes |
| `homeassistant/sensor/solarsage_<id>/config` (retain) | HA discovery config | Written once per widget on first publish; HA auto-creates the entity |

All topics are **retained** so a fresh HA reboot picks up the last
known state without waiting for the next widget refresh.

## Setup

1. **Point at your broker** — add to `backend/.env`:
   ```
   MQTT_BROKER=192.168.4.10
   MQTT_PORT=1883                     # optional, default 1883
   MQTT_USER=solarsage                # optional
   MQTT_PASS=<broker password>        # optional
   MQTT_BASE_TOPIC=solarsage          # optional, default 'solarsage'
   MQTT_DISCOVERY_PREFIX=homeassistant # optional, matches HA default
   ```

2. **Restart** — `scripts/deploy.sh` or `sudo systemctl restart
   solarsage-backend.service`.

3. **Verify** — after the first widget refresh cycle (< 60 s), HA →
   **Settings → Devices & Services** should show a new device
   "SolarSage" with a sensor per widget. Each sensor's attributes
   contain the full data payload.

## Using in HA automations

Because attributes carry the full data, you can pull any widget field
into a template:

```yaml
# Border wait as its own template sensor
template:
  - sensor:
      - name: "Calexico West wait"
        state: >
          {{ state_attr('sensor.solarsage_border', 'data').ports
             | selectattr('port_number', 'eq', '250302') | list
             | map(attribute='pov.standard.delay_minutes') | first }}
        unit_of_measurement: "min"

# AQI trigger
automation:
  - alias: Alexa AQI alert
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('sensor.solarsage_aqi', 'data').current.us_aqi > 100 }}
    action:
      - service: notify.alexa_media_everywhere
        data:
          message: "AQI unhealthy right now"
```

## Overlap with subscriptions

Both MQTT and subscription rules (see [NOTIFICATIONS.md](NOTIFICATIONS.md))
give you push-style reactions. Rules-of-thumb:

* **Subscription rules** — quick declarative "if X then TTS + Telegram",
  managed inside SolarSage. Good for the SolarSage-native channels
  (TTS + HA notify) and things you want to change from the dashboard.
* **HA automations via MQTT** — richer trigger/action language, cross-
  references other HA entities, integrates with the whole HA
  ecosystem. Good when a rule needs "and my presence sensor says I'm
  home" or "and the sun is above horizon".

You can (and should) use both — they don't conflict.

## Troubleshooting

**"MQTT publishing not configured"** in the log → `MQTT_BROKER` is
unset. Set it and restart.

**"MQTT connect failed: …"** → check broker IP + credentials, verify
port 1883 is reachable: `nc -zv <broker> 1883` from the Pi.

**Sensors don't appear in HA** → check HA's MQTT integration is
enabled (Settings → Integrations → MQTT). Discovery prefix must
match — if your HA uses a non-default, set `MQTT_DISCOVERY_PREFIX`.

**State never updates** → each widget only publishes on its refresh
cycle. Force-refresh a specific widget with:
```
curl -sSk -X POST https://<host>/api/widgets/<id>/refresh \
  -H "X-API-Key: <key>"
```
