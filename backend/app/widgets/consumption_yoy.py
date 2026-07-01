"""Consumption year-over-year — today vs same day last year.

Reads the EG4 history SQLite (``samples`` table) for a chosen serial's
consumption field, sums today's and same-day-last-year's kWh totals,
and reports the delta.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiosqlite

from .base import Widget


CONSUMPTION_FIELD_CANDIDATES = (
    "consumptionPower",
    "hometotal",
    "loadPower",
)


async def _first_serial(db_path: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT serial_num FROM samples LIMIT 1"
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def _pick_field(db_path: str, serial: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT field FROM samples WHERE serial_num=?",
            (serial,),
        )
        fields = {row[0] for row in await cur.fetchall()}
    for f in CONSUMPTION_FIELD_CANDIDATES:
        if f in fields:
            return f
    return None


async def _kwh_between(
    db_path: str, serial: str, field: str, start_ms: int, end_ms: int,
) -> float | None:
    """Integrate power samples (W) over the time interval → kWh."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT ts, value FROM samples WHERE serial_num=? AND field=? "
            "AND ts >= ? AND ts < ? ORDER BY ts",
            (serial, field, start_ms, end_ms),
        )
        rows = await cur.fetchall()
    if len(rows) < 2:
        return None
    energy_wh = 0.0
    for (t1, v1), (t2, v2) in zip(rows, rows[1:]):
        dt_h = (t2 - t1) / 1000.0 / 3600.0
        avg_w = (float(v1) + float(v2)) / 2.0
        energy_wh += avg_w * dt_h
    return round(energy_wh / 1000.0, 2)


class ConsumptionYoYWidget(Widget):
    id = "consumption_yoy"
    kind = "consumption_yoy"
    name = "Consumption YoY"
    description = (
        "Today's household load vs. same-day-last-year — integrated from "
        "the EG4 history SQLite. Useful for spotting drifts (new fridge, "
        "leaky AC, whatever)."
    )
    refresh_seconds = 60 * 60
    default_tab = "Solar"
    default_position = 30

    config_schema = {
        "type": "object",
        "properties": {
            "serial": {"type": ["string", "null"],
                       "description": "EG4 inverter serial to compare; leave null to auto-pick"},
            "field":  {"type": ["string", "null"],
                       "description": "Sample field; leave null to auto-pick from candidates"},
        },
    }
    default_config = {"serial": None, "field": None}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        serial = config.get("serial") or await _first_serial(db_path)
        if not serial:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "note": "no samples in history yet",
            }
        field = config.get("field") or await _pick_field(db_path, serial)
        if not field:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "serial": serial,
                "note": "no consumption field found in history",
            }

        # Use local midnight for "today"; look at partial day up to now
        local = datetime.now().astimezone()
        today_start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_ms = int(today_start_local.timestamp() * 1000)
        now_ms = int(local.timestamp() * 1000)

        # Same day last year: same wall-clock window, minus 365 days
        ly_start_ms = today_start_ms - 365 * 86_400_000
        ly_end_ms   = now_ms - 365 * 86_400_000

        today_kwh = await _kwh_between(db_path, serial, field, today_start_ms, now_ms)
        last_year_kwh = await _kwh_between(db_path, serial, field, ly_start_ms, ly_end_ms)

        delta = None
        pct = None
        if today_kwh is not None and last_year_kwh is not None:
            delta = round(today_kwh - last_year_kwh, 2)
            if last_year_kwh:
                pct = round((delta / last_year_kwh) * 100, 1)
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "serial": serial,
            "field": field,
            "today_kwh_partial": today_kwh,
            "last_year_kwh_partial": last_year_kwh,
            "delta_kwh": delta,
            "delta_pct": pct,
            "note": (
                "'Partial' because we're comparing the day-so-far. Both "
                "sides run from local midnight to the same wall-clock time."
                if last_year_kwh is not None else
                "No data for same day last year — first-year running only."
            ),
        }
