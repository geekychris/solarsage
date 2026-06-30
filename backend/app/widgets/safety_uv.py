"""UV / heat-stress widget — Open-Meteo.

Surfaces today's UV-index peak + the apparent-temperature danger window
(apparent temp ≥ 38 °C / 100 °F). Useful for "don't be outside between
X and Y" decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

OM_URL = "https://api.open-meteo.com/v1/forecast"


class UvHeatWidget(Widget):
    id = "uv_heat"
    kind = "uv_heat"
    name = "UV & heat stress"
    description = (
        "Today's peak UV time + apparent-temperature danger window for the "
        "configured location. Source: Open-Meteo."
    )
    refresh_seconds = 60 * 60
    default_tab = "Safety"
    default_position = 30

    config_schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "danger_apparent_f": {"type": "number"},
            "high_uv_threshold": {"type": "number"},
        },
    }
    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "danger_apparent_f": 100.0,
        "high_uv_threshold": 8.0,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "uv_index,apparent_temperature,temperature_2m",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": 2,
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(OM_URL, params=params, timeout=30) as r:
                r.raise_for_status()
                payload = await r.json()

        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        uv = hourly.get("uv_index") or []
        app_t = hourly.get("apparent_temperature") or []
        temp = hourly.get("temperature_2m") or []

        # "Today" is whichever date is most represented; we have ~48 hourly
        # entries starting at the local 00:00 of today.
        if not times:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "lat": lat, "lon": lon, "today": {}, "tomorrow": {},
            }

        def _summarise(slice_idx: tuple[int, int]) -> dict[str, Any]:
            lo, hi = slice_idx
            if lo >= hi:
                return {}
            uvs = uv[lo:hi]
            apps = app_t[lo:hi]
            ts = times[lo:hi]
            peak_uv_i = max(range(len(uvs)), key=lambda i: uvs[i] or 0)
            peak_t_i = max(range(len(apps)), key=lambda i: apps[i] or -99)
            danger_t = float(config.get("danger_apparent_f", 100.0))
            danger_hours = [t for t, a in zip(ts, apps) if (a or 0) >= danger_t]
            return {
                "date": ts[0][:10] if ts else None,
                "peak_uv": {"value": uvs[peak_uv_i], "time": ts[peak_uv_i]},
                "peak_apparent_f": {
                    "value": apps[peak_t_i], "time": ts[peak_t_i],
                },
                "high_temp_f": max((t for t in temp[lo:hi] if t is not None), default=None),
                "danger_window_hours": danger_hours,
                "any_danger": bool(danger_hours),
            }

        # Split the hourly array into today's slice + tomorrow's slice based
        # on the date in each timestamp.
        today_date = times[0][:10]
        split = next(
            (i for i, t in enumerate(times) if t[:10] != today_date),
            len(times),
        )
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "lat": lat, "lon": lon,
            "today": _summarise((0, split)),
            "tomorrow": _summarise((split, len(times))),
        }
