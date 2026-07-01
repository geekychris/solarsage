"""AC vs PV overlay chart — today's PV production, house load, and
smart_ac consumption on the same time axis.

Diagnoses smart_ac scheduling: on a good day the AC line should hug
the PV line while the sun is up. If it climbs after sunset you're
burning battery for cooling — and this chart makes that obvious.

* PV + load come from the EG4 history SQLite (whichever fields the
  inverter reports — auto-detected).
* AC comes from Home Assistant history for each ``input_boolean.ac_<room>``
  entity, integrated over the bucket, multiplied by the room's
  calibrated ``delta_w``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import aiosqlite

from .base import Widget
from .solar_vitals import _fetch_smart_ac  # reuses calibration lookup

log = logging.getLogger("eg4.widgets.acpv_overlay")

BUCKET_MINUTES = 15
LOOKBACK_HOURS = 24


async def _first_serial(db_path: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT DISTINCT serial_num FROM samples LIMIT 1")
        row = await cur.fetchone()
    return row[0] if row else None


async def _fields_for(db_path: str, serial: str) -> set[str]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT field FROM samples WHERE serial_num=?", (serial,),
        )
        return {r[0] for r in await cur.fetchall()}


async def _bucket_avg(
    db_path: str, serial: str, field: str,
    start_ms: int, end_ms: int, bucket_ms: int,
) -> list[float | None]:
    """Return average value per bucket in [start, end)."""
    n_buckets = (end_ms - start_ms) // bucket_ms
    sums = [0.0] * n_buckets
    counts = [0] * n_buckets
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT ts, value FROM samples WHERE serial_num=? AND field=? "
            "AND ts >= ? AND ts < ? ORDER BY ts",
            (serial, field, start_ms, end_ms),
        )
        async for ts, v in cur:
            idx = (ts - start_ms) // bucket_ms
            if 0 <= idx < n_buckets:
                sums[idx] += float(v)
                counts[idx] += 1
    return [
        (sums[i] / counts[i]) if counts[i] else None
        for i in range(n_buckets)
    ]


async def _pv_load_series(
    db_path: str, start_ms: int, end_ms: int, bucket_ms: int,
) -> tuple[list[float | None], list[float | None], str | None, str | None]:
    serial = await _first_serial(db_path)
    if not serial:
        return [], [], None, None
    fields = await _fields_for(db_path, serial)

    pv_field = "ppv" if "ppv" in fields else (
        "ppv1" if "ppv1" in fields else None
    )
    load_field = None
    for candidate in ("consumptionPower", "epsLoadPower", "pEpsL1N"):
        if candidate in fields:
            load_field = candidate
            break

    pv = await _bucket_avg(db_path, serial, pv_field, start_ms, end_ms, bucket_ms) if pv_field else []
    load = await _bucket_avg(db_path, serial, load_field, start_ms, end_ms, bucket_ms) if load_field else []

    # If load field is only a phase, we might want L1+L2 but for now
    # single field is fine — surfaces trend clearly enough for a chart.
    return pv, load, pv_field, load_field


async def _ha_history(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    entity_id: str, start_iso: str, end_iso: str,
) -> list[dict]:
    """Return list of {last_changed, state} for the entity in the window."""
    params = {
        "filter_entity_id": entity_id,
        "end_time": end_iso,
        "minimal_response": "true",
        "no_attributes": "true",
    }
    url = f"{ha_url}/api/history/period/{start_iso}"
    try:
        async with http.get(
            url, params=params,
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=15,
        ) as r:
            if r.status != 200:
                return []
            payload = await r.json()
    except Exception:
        return []
    # payload is a list of lists; take the first entity's series
    if not payload or not isinstance(payload, list) or not payload[0]:
        return []
    return payload[0]


def _integrate_on_minutes_per_bucket(
    history: list[dict], start_ms: int, end_ms: int, bucket_ms: int,
) -> list[float]:
    """For each bucket, how many minutes was the entity in state=on?"""
    n = (end_ms - start_ms) // bucket_ms
    out = [0.0] * n
    if not history:
        return out
    # Build a list of (ts_ms, state) sorted
    events: list[tuple[int, str]] = []
    for h in history:
        lc = h.get("last_changed") or h.get("last_updated")
        if not lc:
            continue
        try:
            dt = datetime.fromisoformat(lc.replace("Z", "+00:00"))
        except ValueError:
            continue
        events.append((int(dt.timestamp() * 1000), str(h.get("state") or "").lower()))
    events.sort()
    if not events:
        return out
    # Prepend a sample at start_ms so we know the initial state
    if events[0][0] > start_ms:
        events.insert(0, (start_ms, events[0][1]))
    # Append a terminator at end_ms
    events.append((end_ms, events[-1][1]))

    for (t1, s1), (t2, _) in zip(events, events[1:]):
        if s1 != "on":
            continue
        # Distribute the [t1, t2) window across buckets
        a = max(t1, start_ms)
        b = min(t2, end_ms)
        if a >= b:
            continue
        while a < b:
            idx = (a - start_ms) // bucket_ms
            bucket_end = start_ms + (idx + 1) * bucket_ms
            chunk_end = min(b, bucket_end)
            out[idx] += (chunk_end - a) / 60000.0
            a = chunk_end
    return out


class AcPvOverlayWidget(Widget):
    id = "acpv_overlay"
    kind = "acpv_overlay"
    name = "AC vs PV overlay"
    description = (
        "Today's PV production and smart_ac consumption on the same "
        "time axis. Live from EG4 history + Home Assistant. If the AC "
        "line hugs the PV curve while the sun is up you're loving free "
        "solar; if it climbs after sunset you're burning battery for "
        "cooling."
    )
    refresh_seconds = 15 * 60
    default_tab = "Solar"
    default_position = 40

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at":  {"type": "string", "format": "date-time"},
            "bucket_minutes": {"type": "integer"},
            "starts_at":   {"type": "string", "format": "date-time"},
            "ends_at":     {"type": "string", "format": "date-time"},
            "times":       {"type": "array", "items": {"type": "string"}},
            "pv_kw":       {"type": "array"},
            "load_kw":     {"type": "array"},
            "ac_kw":       {"type": "array"},
            "per_ac_kw":   {"type": "object"},
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "rooms": {"type": "array", "items": {"type": "string"}},
        },
    }
    default_config = {
        "rooms": ["master", "guest", "dining", "living", "office", "kyle"],
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")

        now = datetime.now(timezone.utc)
        end_ms = int(now.timestamp() * 1000)
        start_ms = end_ms - LOOKBACK_HOURS * 3600 * 1000
        bucket_ms = BUCKET_MINUTES * 60 * 1000
        n = (end_ms - start_ms) // bucket_ms

        # PV + load from EG4 history (Watts)
        pv, load, pv_field, load_field = await _pv_load_series(
            db_path, start_ms, end_ms, bucket_ms,
        )
        pv_kw = [(v / 1000) if v is not None else None for v in (pv or [None] * n)]
        load_kw = [(v / 1000) if v is not None else None for v in (load or [None] * n)]

        # Per-room AC time series from HA history + calibration
        rooms = config.get("rooms") or []
        per_ac_kw: dict[str, list[float]] = {r: [0.0] * n for r in rooms}
        total_ac_kw = [0.0] * n

        if ha_url and ha_token and rooms:
            async with aiohttp.ClientSession() as http:
                # Get current calibration to know watts-per-room
                cal = await _fetch_smart_ac(http, ha_url, ha_token, rooms)
                watts_by_room = {c["room"]: float(c.get("watts") or 0) for c in cal}
                start_iso = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat()
                end_iso = now.isoformat()
                for room in rooms:
                    hist = await _ha_history(
                        http, ha_url, ha_token,
                        f"input_boolean.ac_{room}", start_iso, end_iso,
                    )
                    minutes_on = _integrate_on_minutes_per_bucket(
                        hist, start_ms, end_ms, bucket_ms,
                    )
                    w = watts_by_room.get(room, 0)
                    for i, m in enumerate(minutes_on):
                        kw = (m / BUCKET_MINUTES) * (w / 1000)
                        per_ac_kw[room][i] = round(kw, 3)
                        total_ac_kw[i] = round(total_ac_kw[i] + kw, 3)

        # Time labels — one ISO per bucket start
        times = [
            datetime.fromtimestamp(
                (start_ms + i * bucket_ms) / 1000, tz=timezone.utc,
            ).isoformat()
            for i in range(n)
        ]

        return {
            "fetched_at": now.isoformat(),
            "bucket_minutes": BUCKET_MINUTES,
            "starts_at": times[0] if times else None,
            "ends_at": now.isoformat(),
            "times": times,
            "pv_kw": pv_kw,
            "load_kw": load_kw,
            "ac_kw": total_ac_kw,
            "per_ac_kw": per_ac_kw,
            "pv_field": pv_field,
            "load_field": load_field,
        }
