"""Marine + fishing forecast — Open-Meteo Marine.

Returns wind, wave height, swell, and sea-surface temperature for the
next ~48 hours. Suggests "best fishing window today" using a very simple
heuristic: smaller waves + lighter wind = better, weighted toward
dawn/dusk hours (which the user can validate against the tide widget).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"


class MarineWidget(Widget):
    id = "marine"
    kind = "marine"
    name = "Marine forecast"
    description = (
        "Sea conditions for the configured spot — wave height, wind, sea "
        "temperature — plus a simple 'best fishing window today' pick. "
        "Sources: Open-Meteo (Marine + Atmospheric)."
    )
    refresh_seconds = 60 * 60
    default_tab = "Outdoor"
    default_position = 20

    config_schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
        },
    }
    default_config = {"lat": 31.025, "lon": -114.838}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        marine_params = {
            "latitude": lat, "longitude": lon,
            "hourly": (
                "wave_height,wave_direction,wave_period,"
                "sea_surface_temperature,swell_wave_height"
            ),
            "timezone": "auto",
            "forecast_days": 2,
        }
        wx_params = {
            "latitude": lat, "longitude": lon,
            "hourly": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "wind_speed_unit": "kn",
            "timezone": "auto",
            "forecast_days": 2,
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(MARINE_URL, params=marine_params, timeout=30) as r:
                r.raise_for_status()
                marine = await r.json()
            async with http.get(WEATHER_URL, params=wx_params, timeout=30) as r:
                r.raise_for_status()
                wx = await r.json()

        mh = marine.get("hourly") or {}
        wh = wx.get("hourly") or {}
        # Marine and weather hourly arrays start at the same local 00:00, so
        # they line up index-for-index.
        times = mh.get("time") or []
        rows = []
        for i, t in enumerate(times):
            rows.append({
                "time": t,
                "wave_height_m": _at(mh.get("wave_height"), i),
                "wave_period_s": _at(mh.get("wave_period"), i),
                "swell_m": _at(mh.get("swell_wave_height"), i),
                "sst_c": _at(mh.get("sea_surface_temperature"), i),
                "wind_kn": _at(wh.get("wind_speed_10m"), i),
                "wind_gust_kn": _at(wh.get("wind_gusts_10m"), i),
                "wind_dir": _at(wh.get("wind_direction_10m"), i),
            })

        today_date = times[0][:10] if times else None
        today_rows = [r for r in rows if r["time"][:10] == today_date]
        # Score: lower wave + lower wind + dawn/dusk bonus
        def score(r: dict[str, Any]) -> float:
            wave = r.get("wave_height_m") or 0
            wind = r.get("wind_kn") or 0
            hour = int(r["time"][11:13])
            time_bonus = 0
            if 5 <= hour <= 8 or 17 <= hour <= 20:
                time_bonus = 0.5  # dawn / dusk
            return -wave * 2 - wind * 0.05 + time_bonus
        best = sorted(today_rows, key=score, reverse=True)[:3]
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "lat": lat, "lon": lon,
            "hourly": rows[:48],
            "best_windows_today": [
                {
                    "time": r["time"],
                    "wave_height_m": r["wave_height_m"],
                    "wind_kn": r["wind_kn"],
                    "sst_c": r["sst_c"],
                }
                for r in best
            ],
        }


def _at(arr: list[Any] | None, i: int) -> Any:
    if not arr or i >= len(arr):
        return None
    return arr[i]
