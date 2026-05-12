"""Open-Meteo weather client.

Why Open-Meteo:
  - Free, no API key, no signup, no commercial-use surcharge for hobby loads
  - Returns forecasted shortwave radiation + direct/diffuse split (great for PV)
  - Includes a separate historical archive endpoint for back-modeling AC load
  - Single endpoint per concern, simple JSON

Free-tier limits are generous (~10k calls/day per IP); we cache responses for
15 minutes in-process to be polite when the UI auto-refreshes.

Other free options considered:
  - NOAA/NWS — US-focused, weak in northern Mexico / San Felipe
  - OpenWeatherMap — free tier requires an API key + 1k/day cap
  - WeatherAPI.com, Visual Crossing — free tiers but require keys
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import aiohttp

def _ignore_ssl() -> bool:
    """Read at request time, not import time — main.py's load_dotenv() may
    run after this module is imported, in which case a module-level snapshot
    would miss the value."""
    return os.getenv("EG4_DISABLE_VERIFY_SSL", "0") == "1"

log = logging.getLogger("eg4.weather")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# 15 minute in-process cache. Keyed by (kind, lat, lon, days_or_dates).
_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 15 * 60
_lock = asyncio.Lock()


async def _fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=20)
    connector = aiohttp.TCPConnector(ssl=not _ignore_ssl())
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as s:
        async with s.get(url, params=params) as r:
            if r.status != 200:
                text = await r.text()
                raise RuntimeError(f"open-meteo {url} -> HTTP {r.status}: {text[:400]}")
            return await r.json()


async def forecast(
    lat: float, lon: float, days: int = 7, tz: str = "auto", past_days: int = 0
) -> dict[str, Any]:
    """Hourly forecast for the next `days` days at (lat, lon).

    `past_days` extends the response backwards using Open-Meteo's measured
    values for the recent past (covers today and the few days before, which
    the archive endpoint does not yet have)."""
    key = ("forecast", round(lat, 4), round(lon, 4), days, tz, past_days)
    async with _lock:
        cached = _cache.get(key)
        if cached and (time.time() - cached[0] < _CACHE_TTL):
            return cached[1]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "cloud_cover",
            "wind_speed_10m",
            "shortwave_radiation",  # GHI W/m²
            "direct_normal_irradiance",
            "diffuse_radiation",
            "precipitation_probability",
        ]),
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "cloud_cover",
            "shortwave_radiation",
            "wind_speed_10m",
        ]),
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "sunrise",
            "sunset",
            "shortwave_radiation_sum",
            "precipitation_sum",
            "uv_index_max",
        ]),
        "forecast_days": days,
        "timezone": tz,
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",  # San Felipe lives in °F
    }
    if past_days > 0:
        params["past_days"] = past_days
    data = await _fetch_json(FORECAST_URL, params)
    async with _lock:
        _cache[key] = (time.time(), data)
    return data


async def historical(
    lat: float, lon: float, start_date: str, end_date: str, tz: str = "auto"
) -> dict[str, Any]:
    """Historical hourly archive between start_date and end_date (YYYY-MM-DD)."""
    key = ("hist", round(lat, 4), round(lon, 4), start_date, end_date, tz)
    async with _lock:
        cached = _cache.get(key)
        if cached and (time.time() - cached[0] < _CACHE_TTL):
            return cached[1]
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "cloud_cover",
            "shortwave_radiation",
            "wind_speed_10m",
        ]),
        "timezone": tz,
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
    }
    data = await _fetch_json(ARCHIVE_URL, params)
    async with _lock:
        _cache[key] = (time.time(), data)
    return data
