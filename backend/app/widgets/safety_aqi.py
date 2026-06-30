"""Air quality widget — Open-Meteo air-quality endpoint.

Returns current PM2.5, PM10, O3, US AQI, plus a peak-AQI projection for
the next 24h. No API key needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _aqi_category(aqi: float | None) -> str:
    if aqi is None: return "unknown"
    if aqi <= 50:   return "good"
    if aqi <= 100:  return "moderate"
    if aqi <= 150:  return "unhealthy for sensitive"
    if aqi <= 200:  return "unhealthy"
    if aqi <= 300:  return "very unhealthy"
    return "hazardous"


class AqiWidget(Widget):
    id = "aqi"
    kind = "aqi"
    name = "Air quality"
    description = (
        "Current air quality (US AQI, PM2.5, PM10, ozone, dust) plus the "
        "next-24h peak. Source: Open-Meteo / CAMS."
    )
    refresh_seconds = 60 * 60
    default_tab = "Safety"
    default_position = 40

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
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "us_aqi,pm10,pm2_5,ozone,dust",
            "hourly": "us_aqi,pm2_5,dust",
            "timezone": "auto",
            "forecast_days": 2,
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(AQ_URL, params=params, timeout=30) as r:
                r.raise_for_status()
                payload = await r.json()
        current = payload.get("current") or {}
        hourly = payload.get("hourly") or {}
        us_aqi_h = hourly.get("us_aqi") or []
        dust_h = hourly.get("dust") or []
        times = hourly.get("time") or []
        peak_aqi = None
        peak_time = None
        for t, a in zip(times, us_aqi_h):
            if a is None: continue
            if peak_aqi is None or a > peak_aqi:
                peak_aqi, peak_time = a, t
        peak_dust = None
        peak_dust_time = None
        for t, d in zip(times, dust_h):
            if d is None: continue
            if peak_dust is None or d > peak_dust:
                peak_dust, peak_dust_time = d, t
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "lat": lat, "lon": lon,
            "current": {
                "us_aqi": current.get("us_aqi"),
                "category": _aqi_category(current.get("us_aqi")),
                "pm25": current.get("pm2_5"),
                "pm10": current.get("pm10"),
                "ozone": current.get("ozone"),
                "dust": current.get("dust"),
                "time": current.get("time"),
            },
            "peak_24h": {
                "us_aqi": peak_aqi,
                "category": _aqi_category(peak_aqi),
                "time": peak_time,
            },
            "peak_dust_24h": {
                "ugm3": peak_dust,
                "time": peak_dust_time,
            },
        }
