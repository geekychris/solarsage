"""Solar forecast accuracy tracker.

Compares yesterday's forecast (what we expected) to yesterday's actual
production (what we got), then rolls that up over the last 30 days.
Answers: "is the site's peak_kw setting realistic?" and "do we lean
too optimistic on cloudy days?"

The forecast is re-computed on demand — no separate store of daily
predictions is required. We use the same shortwave-radiation ×
peak_kw model as ``solar_excess`` / ``when_to_run``, but backed out
one day at a time using Open-Meteo's ``archive`` endpoint for real
historical radiation, then compare to the integrated actual power
from the EG4 history.

Refresh cadence is daily — nothing changes intra-day for this metric.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiohttp
import aiosqlite

from .base import Widget

# Open-Meteo historical archive of shortwave radiation (real, not
# forecasted, so we compare apples to apples for past days).
OM_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


async def _first_serial(db_path: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT DISTINCT serial_num FROM samples LIMIT 1")
        row = await cur.fetchone()
    return row[0] if row else None


async def _actual_kwh_for_day(
    db_path: str, serial: str, day: date, tz_offset_minutes: int,
) -> float | None:
    """Integrate ``ppv`` (or ppv1+ppv2) over the local day → kWh."""
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    async with aiosqlite.connect(db_path) as db:
        # Prefer 'ppv' aggregate; else sum ppv1+ppv2 by-timestamp is
        # heavier — settle for ppv1 if ppv isn't present.
        cur = await db.execute(
            "SELECT DISTINCT field FROM samples WHERE serial_num=?", (serial,),
        )
        fields = {r[0] for r in await cur.fetchall()}
        field = "ppv" if "ppv" in fields else ("ppv1" if "ppv1" in fields else None)
        if not field:
            return None
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


async def _read_setting(db_path: str, key: str, default: float) -> float:
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                "SELECT value FROM settings WHERE key=?", (key,),
            )
            row = await cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:  # noqa: BLE001
        pass
    return default


def _forecast_kwh_from_radiation(
    hourly_radiation: list[float | None], peak_kw: float,
) -> float | None:
    """Same model as ``solar_excess``: PV kW ≈ peak_kw × (radiation / 1000).
    Integrate over 24 hourly readings → kWh."""
    total = 0.0
    hits = 0
    for r in hourly_radiation:
        if r is None:
            continue
        pv_kw = peak_kw * (float(r) / 1000.0)
        total += pv_kw    # 1 h buckets → kW × 1h = kWh
        hits += 1
    return round(total, 2) if hits else None


class ForecastAccuracyWidget(Widget):
    id = "forecast_accuracy"
    kind = "forecast_accuracy"
    name = "Forecast accuracy"
    description = (
        "How well did we predict yesterday's PV? Compares the "
        "forecast (peak_kw × shortwave radiation model) to actual "
        "integrated production for the last 30 days. Big red bars "
        "mean the site's ``peak_kw`` setting is too high or too "
        "low — tune it in Settings → System."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Solar"
    default_position = 46

    config_schema = {
        "type": "object",
        "properties": {
            "window_days": {"type": "integer", "minimum": 3, "maximum": 60},
            "lat":         {"type": "number"},
            "lon":         {"type": "number"},
        },
    }
    default_config = {
        "window_days": 30,
        "lat": 31.025,
        "lon": -114.838,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        window_days = int(config.get("window_days", 30))
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))

        serial = await _first_serial(db_path)
        if not serial:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "note": "no samples in history yet",
            }
        peak_kw = await _read_setting(db_path, "peak_kw", 10.0)

        # Local timezone offset (used to align "day" boundaries)
        local_tz = datetime.now().astimezone().tzinfo
        tz_offset_minutes = int(
            (local_tz.utcoffset(datetime.now()) or timedelta()).total_seconds() / 60
        ) if local_tz else 0

        today = datetime.now(local_tz).date()
        start = today - timedelta(days=window_days)
        end = today - timedelta(days=1)  # skip today (in progress)

        # One archive call for the whole range — Open-Meteo is happy
        # with that.
        async with aiohttp.ClientSession() as http:
            params = {
                "latitude": lat, "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "hourly": "shortwave_radiation",
                "timezone": "auto",
            }
            try:
                async with http.get(OM_ARCHIVE, params=params, timeout=30) as r:
                    r.raise_for_status()
                    wx = await r.json()
            except Exception as exc:  # noqa: BLE001
                return {
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "note": f"open-meteo archive failed: {exc}",
                }

        times = (wx.get("hourly") or {}).get("time") or []
        rads = (wx.get("hourly") or {}).get("shortwave_radiation") or []

        # Bucket hourly radiation into per-day arrays
        by_day: dict[str, list[float | None]] = {}
        for t, r_v in zip(times, rads):
            d = t[:10]
            by_day.setdefault(d, []).append(r_v)

        rows = []
        totals = {"forecast_kwh": 0.0, "actual_kwh": 0.0, "days": 0}
        for i in range(window_days):
            d = start + timedelta(days=i)
            if d > end:
                break
            key = d.isoformat()
            forecast_kwh = _forecast_kwh_from_radiation(
                by_day.get(key, []), peak_kw,
            )
            actual_kwh = await _actual_kwh_for_day(
                db_path, serial, d, tz_offset_minutes,
            )
            error_kwh = None
            error_pct = None
            if forecast_kwh is not None and actual_kwh is not None:
                error_kwh = round(actual_kwh - forecast_kwh, 2)
                error_pct = round(
                    100 * error_kwh / max(0.1, forecast_kwh), 1,
                )
                totals["forecast_kwh"] += forecast_kwh
                totals["actual_kwh"] += actual_kwh
                totals["days"] += 1
            rows.append({
                "date": key,
                "forecast_kwh": forecast_kwh,
                "actual_kwh": actual_kwh,
                "error_kwh": error_kwh,
                "error_pct": error_pct,
            })

        summary: dict[str, Any] = {}
        if totals["days"]:
            fc = round(totals["forecast_kwh"] / totals["days"], 2)
            ac = round(totals["actual_kwh"] / totals["days"], 2)
            summary = {
                "days": totals["days"],
                "avg_forecast_kwh": fc,
                "avg_actual_kwh": ac,
                "avg_error_kwh": round(ac - fc, 2),
                "avg_error_pct": round(100 * (ac - fc) / max(0.1, fc), 1),
                "peak_kw_used": peak_kw,
            }

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "window_days": window_days,
            "summary": summary,
            "per_day": rows,
        }
