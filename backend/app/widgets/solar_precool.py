"""Pre-cool advisor widget.

Looks at tomorrow's (and today's) heat profile and recommends a
pre-cool window during the solar-surplus part of the day. The idea: in
desert San Felipe, cooling the thermal mass when energy is free lets
the AC coast through the late-afternoon peak when the sun is low and
the grid is most expensive.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

OM_URL = "https://api.open-meteo.com/v1/forecast"


class PrecoolWidget(Widget):
    id = "precool"
    kind = "precool"
    name = "Pre-cool advisor"
    description = (
        "Suggests a pre-cool window for today and tomorrow based on the "
        "apparent-temperature peak and the solar surplus hours. The "
        "pre-cool window targets the period when shortwave radiation is "
        "highest and ends 2-3 hours before the peak so the thermal mass "
        "carries you through."
    )
    refresh_seconds = 60 * 60
    default_tab = "Solar"
    default_position = 20

    config_schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "trigger_apparent_f": {"type": "number"},
            "precool_hours": {"type": "integer"},
        },
    }
    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "trigger_apparent_f": 95.0,
        "precool_hours": 3,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        trigger = float(config.get("trigger_apparent_f", 95.0))
        precool_h = int(config.get("precool_hours", 3))

        params = {
            "latitude": lat, "longitude": lon,
            "hourly": "apparent_temperature,temperature_2m,shortwave_radiation",
            "temperature_unit": "fahrenheit",
            "timezone": "auto",
            "forecast_days": 2,
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(OM_URL, params=params, timeout=30) as r:
                r.raise_for_status()
                wx = await r.json()

        hourly = wx.get("hourly") or {}
        times = hourly.get("time") or []
        app_t = hourly.get("apparent_temperature") or []
        rad = hourly.get("shortwave_radiation") or []
        if not times:
            return {"fetched_at": datetime.now(timezone.utc).isoformat(),
                    "today": None, "tomorrow": None}

        today_date = times[0][:10]

        def _day_advice(d_idx: tuple[int, int]) -> dict[str, Any]:
            lo, hi = d_idx
            if lo >= hi:
                return {}
            day_times = times[lo:hi]
            day_app = app_t[lo:hi]
            day_rad = rad[lo:hi]
            if not day_times:
                return {}
            peak_i = max(range(len(day_app)), key=lambda i: day_app[i] or -99)
            peak_t = day_app[peak_i]
            peak_time = day_times[peak_i]
            recommend = (peak_t or 0) >= trigger
            # Pre-cool window = the precool_h hours of highest radiation
            # that END at least 2 hours before peak. (If peak is early
            # and there's no qualifying window, fall back to top-N rad
            # hours regardless.)
            peak_hour = int(peak_time[11:13])
            candidates = []
            for i, (t, r_) in enumerate(zip(day_times, day_rad)):
                if r_ is None:
                    continue
                h = int(t[11:13])
                if h > peak_hour - 2:
                    continue
                candidates.append((i, float(r_)))
            candidates.sort(key=lambda x: x[1], reverse=True)
            sel = sorted(c[0] for c in candidates[:precool_h])
            window = [day_times[i] for i in sel] if sel else []
            return {
                "date": day_times[0][:10],
                "peak_apparent_f": peak_t,
                "peak_at": peak_time,
                "recommend_precool": recommend,
                "precool_window": window,
            }

        # Find today / tomorrow boundaries
        split = next(
            (i for i, t in enumerate(times) if t[:10] != today_date),
            len(times),
        )
        today = _day_advice((0, split))
        tomorrow = _day_advice((split, len(times)))
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "lat": lat, "lon": lon,
            "trigger_apparent_f": trigger,
            "today": today,
            "tomorrow": tomorrow,
        }
