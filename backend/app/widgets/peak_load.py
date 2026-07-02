"""Peak-load recorder.

Rolling 30-day maximum simultaneous house load, sampled from the EG4
history SQLite. Surfaces the single-highest reading in the window,
today's peak, and a 30-day distribution so the user can spot the "we
tripped the inverter at 6:47 pm on the 14th" moment before it becomes
a habit.

Uses whichever of ``consumptionPower`` / ``epsLoadPower`` /
``pEpsL1N + pEpsL2N`` the inverter reports.
"""

from __future__ import annotations

import os
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from .base import Widget

CANDIDATE_FIELDS = ("consumptionPower", "epsLoadPower", "pEpsL1N")


async def _first_serial(db_path: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT DISTINCT serial_num FROM samples LIMIT 1")
        row = await cur.fetchone()
    return row[0] if row else None


async def _pick_field(db_path: str, serial: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT field FROM samples WHERE serial_num=?", (serial,),
        )
        fields = {r[0] for r in await cur.fetchall()}
    for f in CANDIDATE_FIELDS:
        if f in fields:
            return f
    return None


class PeakLoadWidget(Widget):
    id = "peak_load"
    kind = "peak_load"
    name = "Peak load"
    description = (
        "Rolling 30-day maximum simultaneous house load. The single "
        "highest sample, when it happened, plus today's peak and a "
        "per-day bar chart. Watch this if your inverter has ever "
        "tripped from an overload — it tells you how close you got."
    )
    refresh_seconds = 10 * 60
    default_tab = "Solar"
    default_position = 45

    config_schema = {
        "type": "object",
        "properties": {
            "window_days": {"type": "integer", "minimum": 1, "maximum": 90},
            "serial":      {"type": ["string", "null"]},
            "field":       {"type": ["string", "null"]},
        },
    }
    default_config = {
        "window_days": 30,
        "serial": None,
        "field": None,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        window_days = int(config.get("window_days", 30))
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
                "note": "no load field in history",
            }

        now_ms = int(_time.time() * 1000)
        start_ms = now_ms - window_days * 86_400_000

        async with aiosqlite.connect(db_path) as db:
            # Overall peak in the window
            cur = await db.execute(
                "SELECT ts, value FROM samples WHERE serial_num=? AND field=? "
                "AND ts >= ? AND ts < ? ORDER BY value DESC LIMIT 1",
                (serial, field, start_ms, now_ms),
            )
            top = await cur.fetchone()
            # Per-day peak
            cur = await db.execute(
                "SELECT ts / 86400000 AS day_ms, MAX(value) FROM samples "
                "WHERE serial_num=? AND field=? AND ts >= ? AND ts < ? "
                "GROUP BY day_ms ORDER BY day_ms",
                (serial, field, start_ms, now_ms),
            )
            per_day = [(int(r[0]), float(r[1])) for r in await cur.fetchall()]
            # Today
            today_start_ms = int(
                datetime.now().astimezone().replace(
                    hour=0, minute=0, second=0, microsecond=0,
                ).timestamp() * 1000
            )
            cur = await db.execute(
                "SELECT ts, MAX(value) FROM samples WHERE serial_num=? AND field=? "
                "AND ts >= ?",
                (serial, field, today_start_ms),
            )
            today_row = await cur.fetchone()

        top_val = None
        top_iso = None
        if top:
            top_val = float(top[1])
            top_iso = datetime.fromtimestamp(
                top[0] / 1000, tz=timezone.utc,
            ).astimezone().isoformat()

        today_kw = None
        today_iso = None
        if today_row and today_row[1] is not None:
            today_kw = float(today_row[1]) / 1000
            today_iso = datetime.fromtimestamp(
                today_row[0] / 1000, tz=timezone.utc,
            ).astimezone().isoformat()

        per_day_out = []
        for day_ms, peak_w in per_day:
            dt = datetime.fromtimestamp(day_ms * 86_400, tz=timezone.utc)
            per_day_out.append({
                "date": dt.date().isoformat(),
                "peak_kw": round(peak_w / 1000, 2),
            })

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "field": field,
            "window_days": window_days,
            "overall_peak_kw": round(top_val / 1000, 2) if top_val else None,
            "overall_peak_at": top_iso,
            "today_peak_kw":   round(today_kw, 2) if today_kw else None,
            "today_peak_at":   today_iso,
            "per_day":         per_day_out,
        }
