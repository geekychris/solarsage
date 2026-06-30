"""Weather widget — current conditions + multi-day forecast.

Open-Meteo provides current, hourly, and daily endpoints; we fold them
into one payload so the dashboard can show a tidy "now / next 7 days"
card. The location defaults to the configured San Felipe coords.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

OM_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherWidget(Widget):
    id = "weather"
    kind = "weather"
    name = "Weather"
    description = (
        "Current conditions + 7-day forecast for the configured location. "
        "Source: Open-Meteo. Used by the Solar excess widget for cloud-"
        "cover adjustments."
    )
    refresh_seconds = 30 * 60
    default_tab = "Outdoor"
    default_position = 5

    config_schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "days": {"type": "integer", "minimum": 1, "maximum": 14},
            "units": {"enum": ["us", "metric"]},
        },
    }
    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "days": 7,
        "units": "us",
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        days = int(config.get("days", 7))
        units = str(config.get("units", "us"))
        temp_unit = "fahrenheit" if units == "us" else "celsius"
        wind_unit = "mph" if units == "us" else "kmh"
        precip_unit = "inch" if units == "us" else "mm"

        params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,cloud_cover,wind_speed_10m,wind_direction_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "apparent_temperature_max,sunrise,sunset,uv_index_max,"
                "precipitation_sum,precipitation_probability_max,"
                "wind_speed_10m_max,cloud_cover_mean"
            ),
            "hourly": "temperature_2m,precipitation_probability,cloud_cover",
            "temperature_unit": temp_unit,
            "wind_speed_unit": wind_unit,
            "precipitation_unit": precip_unit,
            "timezone": "auto",
            "forecast_days": days,
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(OM_URL, params=params, timeout=30) as r:
                r.raise_for_status()
                wx = await r.json()

        current = wx.get("current") or {}
        daily = wx.get("daily") or {}

        days_out = []
        for i, d in enumerate(daily.get("time") or []):
            days_out.append({
                "date": d,
                "weather_code": _at(daily.get("weather_code"), i),
                "high": _at(daily.get("temperature_2m_max"), i),
                "low":  _at(daily.get("temperature_2m_min"), i),
                "feels_max": _at(daily.get("apparent_temperature_max"), i),
                "sunrise":   _at(daily.get("sunrise"), i),
                "sunset":    _at(daily.get("sunset"), i),
                "uv_index_max": _at(daily.get("uv_index_max"), i),
                "precip_sum":  _at(daily.get("precipitation_sum"), i),
                "precip_prob": _at(daily.get("precipitation_probability_max"), i),
                "wind_max":    _at(daily.get("wind_speed_10m_max"), i),
                "cloud_mean_pct": _at(daily.get("cloud_cover_mean"), i),
            })
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "lat": lat, "lon": lon, "units": units,
            "current": {
                "time": current.get("time"),
                "temp": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "cloud_pct": current.get("cloud_cover"),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_dir": current.get("wind_direction_10m"),
                "weather_code": current.get("weather_code"),
            },
            "daily": days_out,
        }


def _at(arr: list[Any] | None, i: int) -> Any:
    if not arr or i >= len(arr):
        return None
    return arr[i]
