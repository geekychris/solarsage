"""Excess-energy planner widget.

Computes a rough kWh surplus envelope for today from:

* the configured site's ``peak_kw`` and ``battery_capacity_kwh`` (read
  from the existing settings KV table),
* tomorrow / today cloud cover from Open-Meteo,
* an assumed household baseline (configurable; default 15 kWh/day).

Returns the estimated kWh excess + a ranked list of suggested loads that
the user could schedule into the midday surplus window. This widget is
intentionally heuristic — the EG4 module already has higher-fidelity
forecasts on ``/api/forecast/excess`` for the dashboard's Today tab.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiohttp
import aiosqlite

from .base import Widget

OM_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_LOADS = [
    {"name": "EV charge (slow)", "kwh": 7.0, "ideal_hours": [10, 11, 12, 13, 14]},
    {"name": "Pool pump (4h)",   "kwh": 4.0, "ideal_hours": [10, 11, 12, 13]},
    {"name": "Dishwasher",       "kwh": 1.5, "ideal_hours": [11, 12, 13]},
    {"name": "Laundry (warm)",   "kwh": 1.0, "ideal_hours": [11, 12, 13, 14]},
    {"name": "Pre-cool house",   "kwh": 6.0, "ideal_hours": [12, 13, 14, 15]},
]


async def _read_setting(db_path: str, key: str, default: float) -> float:
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                "SELECT value FROM settings WHERE key=?", (key,),
            )
            row = await cur.fetchone()
            if row and row[0] not in (None, ""):
                return float(row[0])
    except Exception:
        pass
    return default


class SolarExcessWidget(Widget):
    id = "solar_excess"
    kind = "solar_excess"
    name = "Excess-energy planner"
    description = (
        "Today's expected solar surplus + suggested loads to schedule "
        "into the midday window. Heuristic — combines site peak_kw with "
        "Open-Meteo cloud cover. For higher-fidelity numbers see the "
        "Today tab in the main solar dashboard."
    )
    refresh_seconds = 60 * 60
    default_tab = "Solar"
    default_position = 10

    config_schema = {
        "type": "object",
        "properties": {
            "household_baseline_kwh": {"type": "number"},
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "loads": {"type": "array"},
        },
    }
    default_config = {
        "household_baseline_kwh": 15.0,
        "lat": 31.025,
        "lon": -114.838,
        "loads": DEFAULT_LOADS,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        peak_kw = await _read_setting(db_path, "peak_kw", 10.0)
        battery_kwh = await _read_setting(db_path, "battery_capacity_kwh", 14.3)

        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        baseline = float(config.get("household_baseline_kwh", 15.0))

        async with aiohttp.ClientSession() as http:
            async with http.get(OM_URL, params={
                "latitude": lat, "longitude": lon,
                "daily": "cloud_cover_mean,sunshine_duration",
                "hourly": "cloud_cover,shortwave_radiation",
                "timezone": "auto",
                "forecast_days": 2,
            }, timeout=30) as r:
                r.raise_for_status()
                wx = await r.json()

        daily = wx.get("daily") or {}
        hourly = wx.get("hourly") or {}
        cloud_mean = (daily.get("cloud_cover_mean") or [50.0])[0]
        sun_seconds = (daily.get("sunshine_duration") or [0])[0]
        sun_hours = float(sun_seconds) / 3600.0

        # Clear-sky baseline: peak_kw × typical 5.5h-equivalent for desert
        # site; degrade by mean cloud cover; widen if sunshine is long.
        cloud_factor = max(0.2, 1.0 - float(cloud_mean) / 130.0)
        clear_kwh = float(peak_kw) * 5.5
        produced_kwh = round(clear_kwh * cloud_factor, 1)
        excess_kwh = round(max(0.0, produced_kwh - baseline), 1)
        battery_share = round(min(excess_kwh, float(battery_kwh)), 1)
        surplus_to_grid = round(max(0.0, excess_kwh - battery_share), 1)

        # Best surplus window: hours with highest shortwave radiation today
        times = hourly.get("time") or []
        rad = hourly.get("shortwave_radiation") or []
        today_date = times[0][:10] if times else None
        windows = []
        for t, r in zip(times, rad):
            if r is None or t[:10] != today_date:
                continue
            windows.append((t, float(r)))
        windows.sort(key=lambda x: x[1], reverse=True)
        best_window = sorted(w[0] for w in windows[:4])

        # Rank suggested loads to fit within excess_kwh
        loads = list(config.get("loads") or DEFAULT_LOADS)
        remaining = excess_kwh
        suggested = []
        for ld in loads:
            kwh = float(ld.get("kwh", 0))
            if kwh <= remaining + 0.1:
                suggested.append({**ld, "fits": True})
                remaining = max(0.0, remaining - kwh)
            else:
                suggested.append({**ld, "fits": False})

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "site": {
                "peak_kw": peak_kw,
                "battery_kwh": battery_kwh,
                "lat": lat, "lon": lon,
            },
            "today": {
                "date": today_date,
                "cloud_mean_pct": cloud_mean,
                "sunshine_hours": round(sun_hours, 1),
                "estimated_production_kwh": produced_kwh,
                "household_baseline_kwh": baseline,
                "estimated_excess_kwh": excess_kwh,
                "battery_can_absorb_kwh": battery_share,
                "surplus_to_grid_kwh": surplus_to_grid,
                "best_surplus_window": best_window,
            },
            "suggested_loads": suggested,
        }
