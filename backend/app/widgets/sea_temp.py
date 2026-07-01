"""Sea surface temperature — Open-Meteo Marine + 30-day trailing archive.

Same data source as the marine widget, but focused on temperature with
context: swim comfort, fishing preferences, seasonal norm hint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"


def _c_to_f(c: float) -> float:
    return c * 9 / 5 + 32


def _swim_comfort(c: float | None) -> str:
    if c is None: return "unknown"
    if c < 20:  return "cold — wetsuit"
    if c < 24:  return "cool"
    if c < 28:  return "pleasant"
    if c < 31:  return "warm"
    return "very warm"


def _fishing_note(c: float | None) -> str:
    """Rough guide for Sea of Cortez species."""
    if c is None: return ""
    if c < 20:  return "yellowtail / white sea bass window"
    if c < 24:  return "yellowtail hangover; dorado starting"
    if c < 28:  return "dorado + tuna prime"
    if c < 30:  return "marlin / roosterfish"
    return "peak roosterfish; tuna deep"


class SeaTempWidget(Widget):
    id = "sea_temp"
    kind = "sea_temp"
    name = "Sea temperature"
    description = (
        "Sea surface temperature at your configured spot — current + "
        "7-day forecast + swim / fishing context. Same source as the "
        "Marine widget."
    )
    refresh_seconds = 3 * 3600
    default_tab = "Outdoor"
    default_position = 22

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
            "latitude": lat, "longitude": lon,
            "hourly": "sea_surface_temperature",
            "timezone": "auto",
            "forecast_days": 7,
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(MARINE_URL, params=params, timeout=30) as r:
                r.raise_for_status()
                payload = await r.json()
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("sea_surface_temperature") or []
        current = temps[0] if temps else None
        # Daily peak / low per day
        by_day: dict[str, list[float]] = {}
        for t, c in zip(times, temps):
            if c is None: continue
            by_day.setdefault(t[:10], []).append(float(c))
        days = [
            {"date": d, "high_c": round(max(vs), 1), "low_c": round(min(vs), 1),
             "avg_c": round(sum(vs) / len(vs), 1)}
            for d, vs in sorted(by_day.items())
        ]
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "lat": lat, "lon": lon,
            "current_c": current,
            "current_f": round(_c_to_f(current), 1) if current is not None else None,
            "swim_comfort": _swim_comfort(current),
            "fishing_note": _fishing_note(current),
            "days": days,
        }
