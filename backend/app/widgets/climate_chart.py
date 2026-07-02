"""Temperature + humidity history chart for a configurable set of
Home Assistant sensors. Reads HA's ``/api/history/period`` endpoint
once per configured entity per refresh, downsamples into fixed-size
time buckets, and returns a per-sensor series ready to plot.

By convention we share the ``room_sensors`` list format with
``solar_vitals`` — an entry is ``{name, temp_entity, humidity_entity}``
— so the same three sensors surface on both widgets without
double-configuration.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .base import Widget
from .store import WidgetStore

log = logging.getLogger("eg4.widgets.climate_chart")


async def _ha_history(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    entity_id: str, start_iso: str, end_iso: str,
) -> list[dict]:
    params = {
        "filter_entity_id": entity_id,
        "end_time": end_iso,
        "minimal_response": "true",
        "no_attributes": "true",
    }
    try:
        async with http.get(
            f"{ha_url}/api/history/period/{start_iso}",
            params=params,
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=20,
        ) as r:
            if r.status != 200:
                return []
            payload = await r.json()
    except Exception:  # noqa: BLE001
        return []
    if not payload or not isinstance(payload, list) or not payload[0]:
        return []
    return payload[0]


def _bucket_series(
    history: list[dict], start_ms: int, end_ms: int, bucket_ms: int,
) -> list[float | None]:
    """Return the mean value per bucket in [start, end)."""
    n = (end_ms - start_ms) // bucket_ms
    sums = [0.0] * n
    counts = [0] * n
    for h in history:
        state = h.get("state")
        try:
            v = float(state)
        except (TypeError, ValueError):
            continue
        lc = h.get("last_changed") or h.get("last_updated")
        if not lc:
            continue
        try:
            dt = datetime.fromisoformat(lc.replace("Z", "+00:00"))
        except ValueError:
            continue
        ts_ms = int(dt.timestamp() * 1000)
        idx = (ts_ms - start_ms) // bucket_ms
        if 0 <= idx < n:
            sums[idx] += v
            counts[idx] += 1
    out: list[float | None] = []
    last = None
    for i in range(n):
        if counts[i]:
            v = sums[i] / counts[i]
            out.append(round(v, 2))
            last = v
        else:
            # Carry-forward from the last non-empty bucket so gaps
            # don't chop the line into disconnected fragments.
            out.append(round(last, 2) if last is not None else None)
    return out


class ClimateChartWidget(Widget):
    id = "climate_chart"
    kind = "climate_chart"
    name = "Room climate history"
    description = (
        "Temperature and humidity history for the configured room "
        "sensors over a 24-hour or 7-day window. Reads Home Assistant "
        "history and buckets it into 15-minute (24h) or 1-hour (7d) "
        "averages. Same sensor list format as solar_vitals — either "
        "widget's config works."
    )
    refresh_seconds = 20 * 60
    default_tab = "Solar"
    # Sit right after solar_vitals (position 3) so the chart is next
    # to the live temperature/humidity readout.
    default_position = 5

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at":     {"type": "string", "format": "date-time"},
            "window_hours":   {"type": "integer"},
            "bucket_minutes": {"type": "integer"},
            "starts_at":      {"type": "string", "format": "date-time"},
            "ends_at":        {"type": "string", "format": "date-time"},
            "times":          {"type": "array", "items": {"type": "string"}},
            "sensors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":         {"type": "string"},
                        "temp_series":  {"type": ["array", "null"]},
                        "temp_unit":    {"type": "string"},
                        "humidity_series": {"type": ["array", "null"]},
                        "humidity_unit":   {"type": "string"},
                    },
                },
            },
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "window_hours": {"type": "integer", "minimum": 6, "maximum": 168},
            "sensors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":            {"type": "string"},
                        "temp_entity":     {"type": "string"},
                        "humidity_entity": {"type": "string"},
                    },
                },
            },
        },
    }

    default_config = {
        "window_hours": 24,
        # Empty by default — the widget reads solar_vitals'
        # ``room_sensors`` list so renames flow through without
        # double-configuration. Set this list explicitly (via widget
        # config) only if you want the chart to show a different set
        # from what Solar Vitals renders.
        "sensors": [],
    }

    async def _resolve_sensors(
        self, config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Explicit ``sensors`` on this widget wins; otherwise borrow
        from ``solar_vitals.room_sensors`` so renames stay in one place."""
        explicit = config.get("sensors")
        if isinstance(explicit, list) and explicit:
            return explicit
        try:
            store = WidgetStore(os.getenv("EG4_DB_PATH", "./eg4_history.db"))
            sv_cfg = await store.get_config("solar_vitals") or {}
        except Exception:  # noqa: BLE001
            sv_cfg = {}
        return sv_cfg.get("room_sensors") or []

    def ha_entities_for(self, config):
        entries = super().ha_entities_for(config)
        # Show the effective sensor list — falls back to solar_vitals'
        # ``room_sensors`` when this widget's ``sensors`` is empty, so
        # the tab reflects what the chart actually plots.
        explicit = config.get("sensors")
        if not (isinstance(explicit, list) and explicit):
            try:
                # Synchronous access to widget_config for meta purposes only.
                # ``ha_entities_for`` isn't async; keep this cheap.
                import sqlite3
                db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
                con = sqlite3.connect(db_path)
                row = con.execute(
                    "SELECT config_json FROM widget_config WHERE widget_id=?",
                    ("solar_vitals",),
                ).fetchone()
                con.close()
                if row and row[0]:
                    import json as _json
                    sv_cfg = _json.loads(row[0])
                    explicit = sv_cfg.get("room_sensors") or []
                else:
                    explicit = []
            except Exception:  # noqa: BLE001
                explicit = []
        for i, s in enumerate(explicit):
            name = s.get("name") or f"Sensor {i+1}"
            for k, kind in (("temp_entity", "temp"),
                            ("humidity_entity", "humidity")):
                eid = s.get(k) or ""
                if not eid:
                    continue
                entries.append({
                    "key": f"climate:{i}:{k}",
                    "label": f"{name} — {kind}",
                    "domain": "sensor",
                    "required": False,
                    "entity_id": eid,
                    "read_only": True,
                })
        return entries

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            raise RuntimeError("HA_URL + HA_TOKEN not set in backend/.env")

        window_hours = int(config.get("window_hours", 24))
        # 24h → 15-min buckets (96), 7d → 1-h buckets (168).
        bucket_minutes = 15 if window_hours <= 48 else 60

        now = datetime.now(timezone.utc)
        end_ms = int(now.timestamp() * 1000)
        start_ms = end_ms - window_hours * 3600 * 1000
        bucket_ms = bucket_minutes * 60 * 1000
        n = (end_ms - start_ms) // bucket_ms
        start_iso = datetime.fromtimestamp(
            start_ms / 1000, tz=timezone.utc,
        ).isoformat()
        end_iso = now.isoformat()

        sensors_cfg = await self._resolve_sensors(config)

        sensors_out: list[dict[str, Any]] = []
        async with aiohttp.ClientSession() as http:
            for i, s in enumerate(sensors_cfg):
                name = s.get("name") or f"Sensor {i+1}"
                temp_eid = s.get("temp_entity") or ""
                hum_eid = s.get("humidity_entity") or ""
                temp_series = None
                hum_series = None
                temp_unit = ""
                hum_unit = ""
                if temp_eid:
                    hist = await _ha_history(
                        http, ha_url, ha_token, temp_eid,
                        start_iso, end_iso,
                    )
                    temp_series = _bucket_series(hist, start_ms, end_ms, bucket_ms)
                    # Infer unit from the most recent state
                    async with http.get(
                        f"{ha_url}/api/states/{temp_eid}",
                        headers={"Authorization": f"Bearer {ha_token}"},
                        timeout=10,
                    ) as r:
                        if r.status == 200:
                            payload = await r.json()
                            temp_unit = (payload.get("attributes") or {}).get(
                                "unit_of_measurement", "",
                            )
                if hum_eid:
                    hist = await _ha_history(
                        http, ha_url, ha_token, hum_eid,
                        start_iso, end_iso,
                    )
                    hum_series = _bucket_series(hist, start_ms, end_ms, bucket_ms)
                    async with http.get(
                        f"{ha_url}/api/states/{hum_eid}",
                        headers={"Authorization": f"Bearer {ha_token}"},
                        timeout=10,
                    ) as r:
                        if r.status == 200:
                            payload = await r.json()
                            hum_unit = (payload.get("attributes") or {}).get(
                                "unit_of_measurement", "%",
                            )
                sensors_out.append({
                    "name": name,
                    "temp_entity_id": temp_eid or None,
                    "temp_series": temp_series,
                    "temp_unit": temp_unit,
                    "humidity_entity_id": hum_eid or None,
                    "humidity_series": hum_series,
                    "humidity_unit": hum_unit,
                })

        times = [
            datetime.fromtimestamp(
                (start_ms + i * bucket_ms) / 1000, tz=timezone.utc,
            ).isoformat()
            for i in range(n)
        ]

        return {
            "fetched_at": now.isoformat(),
            "window_hours": window_hours,
            "bucket_minutes": bucket_minutes,
            "starts_at": times[0] if times else None,
            "ends_at": now.isoformat(),
            "times": times,
            "sensors": sensors_out,
        }
