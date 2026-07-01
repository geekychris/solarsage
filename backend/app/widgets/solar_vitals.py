"""Solar Vitals — a glance-at-the-room summary of the solar system.

Answers the questions you actually ask a wall display:

    * What's my battery at right now?
    * How much power is coming from the panels?
    * How much are we using?
    * If we keep going like this, when's the battery full? Or empty?
    * When do I need to start turning things off?

All values are read directly from the EG4 history SQLite so the widget
works without a live EG4 session. Latest sample within the last ~15
minutes is treated as "now".
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

from .base import Widget


SOC_CANDIDATES  = ("soc", "unit0_soc", "batterySoc")
PV_CANDIDATES   = ("ppv", "unit0_ppv", "solarPower")
LOAD_CANDIDATES = ("consumptionPower", "loadPower", "unit0_load")
# Fallback: sum per-string PV
PV_SUM_FIELDS   = ("ppv1", "ppv2", "ppv3", "ppv4")

RECENT_WINDOW_MS = 15 * 60 * 1000       # look this far back for "now"


async def _first_serial(db_path: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT DISTINCT serial_num FROM samples LIMIT 1")
        row = await cur.fetchone()
        return row[0] if row else None


async def _fields_for_serial(db_path: str, serial: str) -> set[str]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT field FROM samples WHERE serial_num=?", (serial,),
        )
        return {row[0] for row in await cur.fetchall()}


async def _latest(
    db_path: str, serial: str, field: str,
) -> tuple[float | None, int | None]:
    """Latest sample of ``field`` within the recent window."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT ts, value FROM samples WHERE serial_num=? AND field=? "
            "ORDER BY ts DESC LIMIT 1",
            (serial, field),
        )
        row = await cur.fetchone()
    if not row:
        return None, None
    return float(row[1]), int(row[0])


async def _latest_sum(
    db_path: str, serial: str, fields: tuple[str, ...],
) -> tuple[float | None, int | None]:
    """Sum the latest value across several fields (e.g. ppv1..ppv4)."""
    total = 0.0
    latest_ts: int | None = None
    any_hit = False
    for f in fields:
        v, ts = await _latest(db_path, serial, f)
        if v is None:
            continue
        any_hit = True
        total += v
        if ts is not None:
            latest_ts = ts if latest_ts is None else max(latest_ts, ts)
    return (total if any_hit else None), latest_ts


async def _read_setting(db_path: str, key: str, default: float) -> float:
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
        if row and row[0] not in (None, ""):
            return float(row[0])
    except Exception:
        pass
    return default


async def _pick_field(
    db_path: str, serial: str, candidates: tuple[str, ...],
    available: set[str],
) -> str | None:
    for f in candidates:
        if f in available:
            return f
    return None


def _fmt_hours_minutes(hours: float) -> str:
    total_min = int(round(hours * 60))
    h, m = divmod(total_min, 60)
    if h == 0:
        return f"{m} min"
    if m == 0:
        return f"{h} h"
    return f"{h} h {m} min"


def _target_time_iso(hours: float) -> str:
    return (
        datetime.now().astimezone() + timedelta(hours=hours)
    ).isoformat()


class SolarVitalsWidget(Widget):
    id = "solar_vitals"
    kind = "solar_vitals"
    name = "Solar vitals"
    description = (
        "Room-glance solar summary — battery SoC, solar production, "
        "house load, projected time to full or empty at the current "
        "rate, and a 'conserve after' cut-back projection. Great for "
        "the rotation full-screen view."
    )
    refresh_seconds = 60
    default_tab = "Solar"
    default_position = 3

    config_schema = {
        "type": "object",
        "properties": {
            "serial": {"type": ["string", "null"]},
            "cut_back_soc": {"type": "number",
                             "description": "Battery % at which the widget flags 'start conserving'"},
        },
    }
    default_config = {"serial": None, "cut_back_soc": 30}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        serial = config.get("serial") or await _first_serial(db_path)
        if not serial:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "note": "no EG4 samples in history yet",
            }

        available = await _fields_for_serial(db_path, serial)
        soc_field  = await _pick_field(db_path, serial, SOC_CANDIDATES,  available)
        pv_field   = await _pick_field(db_path, serial, PV_CANDIDATES,   available)
        load_field = await _pick_field(db_path, serial, LOAD_CANDIDATES, available)

        soc_v, soc_ts = (await _latest(db_path, serial, soc_field)) if soc_field else (None, None)

        if pv_field:
            pv_v, pv_ts = await _latest(db_path, serial, pv_field)
        else:
            pv_v, pv_ts = await _latest_sum(db_path, serial, PV_SUM_FIELDS)

        load_v, load_ts = (await _latest(db_path, serial, load_field)) if load_field else (None, None)

        capacity_kwh = await _read_setting(db_path, "battery_capacity_kwh", 14.3)
        cut_back_soc = float(config.get("cut_back_soc", 30))

        pv_kw   = (pv_v   / 1000) if pv_v   is not None else None
        load_kw = (load_v / 1000) if load_v is not None else None
        net_kw  = None if (pv_kw is None or load_kw is None) else round(pv_kw - load_kw, 3)

        # Time to full or empty
        projection: dict[str, Any] | None = None
        if soc_v is not None and net_kw is not None and abs(net_kw) > 0.05:
            if net_kw > 0 and soc_v < 100:
                remaining_kwh = ((100 - soc_v) / 100.0) * capacity_kwh
                hours = remaining_kwh / net_kw
                projection = {
                    "direction": "charging",
                    "hours": round(hours, 2),
                    "pretty": _fmt_hours_minutes(hours),
                    "target_at": _target_time_iso(hours),
                    "target_soc": 100,
                }
            elif net_kw < 0 and soc_v > 0:
                remaining_kwh = (soc_v / 100.0) * capacity_kwh
                hours = remaining_kwh / abs(net_kw)
                projection = {
                    "direction": "discharging",
                    "hours": round(hours, 2),
                    "pretty": _fmt_hours_minutes(hours),
                    "target_at": _target_time_iso(hours),
                    "target_soc": 0,
                }

        # Conserve-after: at current discharge rate, when will SoC hit cut_back?
        cut_back: dict[str, Any] | None = None
        if (soc_v is not None and net_kw is not None and net_kw < -0.05
                and soc_v > cut_back_soc):
            hours = ((soc_v - cut_back_soc) / 100.0) * capacity_kwh / abs(net_kw)
            cut_back = {
                "target_soc": cut_back_soc,
                "hours": round(hours, 2),
                "pretty": _fmt_hours_minutes(hours),
                "at": _target_time_iso(hours),
            }

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "serial": serial,
            "battery_capacity_kwh": capacity_kwh,
            "soc": soc_v,
            "soc_ts": soc_ts,
            "pv_kw": round(pv_kw, 3) if pv_kw is not None else None,
            "load_kw": round(load_kw, 3) if load_kw is not None else None,
            "net_kw": net_kw,
            "state": (
                "charging" if net_kw and net_kw > 0.05
                else "discharging" if net_kw and net_kw < -0.05
                else "steady"
            ),
            "projection": projection,
            "cut_back": cut_back,
            "fields_used": {
                "soc": soc_field, "pv": pv_field, "load": load_field,
            },
        }
