"""When-to-run recommender.

For each configured high-load appliance (pool pump, dishwasher, laundry,
EV charger, etc.), predict the best contiguous window today or tomorrow
where forecast excess PV covers the appliance's draw. Reads Open-Meteo
for hourly shortwave radiation and pairs it with the site's peak_kw to
build an hourly PV estimate. The house's cached baseline load is
subtracted to yield "excess kW" per hour.

The output is a *recommendation*, not an automation — the frontend
shows a "Start at 10:15 am — free solar covers it" card per appliance.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import aiosqlite

from .base import Widget

OM_URL = "https://api.open-meteo.com/v1/forecast"


DEFAULT_APPLIANCES = [
    {"name": "Laundry (washer)",  "kw": 1.5, "hours": 1.5, "priority": 1},
    {"name": "Dishwasher",        "kw": 1.2, "hours": 1.5, "priority": 2},
    {"name": "Pool pump",         "kw": 1.1, "hours": 4.0, "priority": 3, "enabled": False},
    {"name": "EV charger (L2)",   "kw": 7.2, "hours": 3.0, "priority": 4, "enabled": False},
    {"name": "Water heater boost", "kw": 4.5, "hours": 1.0, "priority": 5, "enabled": False},
]


async def _read_setting(db_path: str, key: str, default: float) -> float:
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                "SELECT value FROM settings WHERE key=?", (key,),
            )
            row = await cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return default


def _best_window(
    hourly_excess: list[float | None], hours_needed: float,
) -> tuple[int, float, float] | None:
    """Sliding window over hourly excess. Returns (start_idx, total_kwh,
    min_kw_in_window) or None if no window covers the appliance."""
    n_slots = max(1, int(round(hours_needed)))
    if n_slots > len(hourly_excess):
        return None
    best = None
    for i in range(0, len(hourly_excess) - n_slots + 1):
        slot = hourly_excess[i:i + n_slots]
        if any(v is None for v in slot):
            continue
        min_kw = min(slot)
        total_kwh = sum(slot)
        if best is None or total_kwh > best[1]:
            best = (i, total_kwh, min_kw)
    return best


class WhenToRunWidget(Widget):
    id = "when_to_run"
    kind = "when_to_run"
    name = "When to run"
    description = (
        "For each high-load appliance you configure, recommends the best "
        "contiguous window today (or tomorrow) where forecast excess "
        "solar covers the appliance's draw. Not an automation — "
        "surfaces a 'run this at 10:15' hint so the user decides."
    )
    refresh_seconds = 60 * 60
    default_tab = "Solar"
    default_position = 25

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at": {"type": "string", "format": "date-time"},
            "site": {"type": "object"},
            "hourly": {"type": "array"},
            "recommendations": {"type": "array"},
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "lat":         {"type": "number"},
            "lon":         {"type": "number"},
            "baseline_kw": {"type": "number"},
            "peak_kw_override": {"type": ["number", "null"]},
            "appliances":  {"type": "array"},
        },
    }

    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "baseline_kw": 0.6,
        "peak_kw_override": None,
        "appliances": DEFAULT_APPLIANCES,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        peak_kw = float(
            config.get("peak_kw_override")
            or await _read_setting(db_path, "peak_kw", 10.0),
        )
        lat = float(config.get("lat") or os.getenv("SOLARSAGE_LAT", "31.025"))
        lon = float(config.get("lon") or os.getenv("SOLARSAGE_LON", "-114.838"))
        baseline_kw = float(config.get("baseline_kw", 0.6))

        async with aiohttp.ClientSession() as http:
            async with http.get(OM_URL, params={
                "latitude": lat, "longitude": lon,
                "hourly": "shortwave_radiation,cloud_cover",
                "timezone": "auto",
                "forecast_days": 2,
            }, timeout=30) as r:
                r.raise_for_status()
                wx = await r.json()

        hourly = wx.get("hourly") or {}
        times: list[str] = hourly.get("time") or []
        rad: list[float | None] = hourly.get("shortwave_radiation") or []

        # Only include hours from now forward
        now = datetime.now().astimezone()
        cutoff = now.replace(minute=0, second=0, microsecond=0)

        hourly_out = []
        for t, r_v in zip(times, rad):
            try:
                t_dt = datetime.fromisoformat(t).replace(
                    tzinfo=now.tzinfo,
                )
            except ValueError:
                continue
            if t_dt < cutoff:
                continue
            # Convert shortwave radiation (W/m²) → PV kW estimate.
            # Empirical scaling: 1000 W/m² ≈ peak_kw (STC).
            pv_kw = None if r_v is None else round(peak_kw * (float(r_v) / 1000), 2)
            excess_kw = None if pv_kw is None else round(
                max(0.0, pv_kw - baseline_kw), 2,
            )
            hourly_out.append({
                "time": t_dt.isoformat(),
                "pv_kw": pv_kw,
                "excess_kw": excess_kw,
            })

        excess_series = [h["excess_kw"] for h in hourly_out]

        appliances = list(config.get("appliances") or DEFAULT_APPLIANCES)
        recs = []
        for a in appliances:
            if a.get("enabled") is False:
                continue
            kw = float(a.get("kw", 0))
            hours = float(a.get("hours", 1))
            # An appliance "fits" a window when the minimum hourly
            # excess across the window is ≥ its draw.
            best = _best_window(excess_series, hours)
            if not best:
                recs.append({**a, "recommend": None,
                             "reason": "no forecast horizon"})
                continue
            idx, total_kwh, min_kw = best
            start = hourly_out[idx]["time"]
            end_dt = datetime.fromisoformat(start) + timedelta(hours=hours)
            fits = min_kw >= kw
            if fits:
                reason = (
                    f"free solar covers it — "
                    f"excess ≥ {min_kw:.1f} kW during the window"
                )
            else:
                deficit_kw = kw - min_kw
                reason = (
                    f"partial — draws ~{deficit_kw:.1f} kW from battery "
                    f"during the softest hour"
                )
            recs.append({
                **a,
                "recommend": {
                    "start": start,
                    "end": end_dt.isoformat(),
                    "min_kw_excess": round(min_kw, 2),
                    "total_kwh_excess": round(total_kwh, 2),
                    "fits": fits,
                },
                "reason": reason,
            })

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "site": {
                "lat": lat, "lon": lon,
                "peak_kw": peak_kw, "baseline_kw": baseline_kw,
            },
            "hourly": hourly_out,
            "recommendations": recs,
        }
