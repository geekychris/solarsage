"""Sun + moon widget — local astronomical calculation, no API needed.

Sunrise/sunset use the NOAA approximation (good to a few seconds for
mid-latitudes). Moon phase uses a simple synodic-month model
(0.0 = new, 0.5 = full).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .base import Widget

# Reference new moon: 2000-01-06 18:14 UT
MOON_EPOCH = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
SYNODIC_MONTH_DAYS = 29.530588853


def _moon_phase(now: datetime) -> dict[str, Any]:
    days = (now - MOON_EPOCH).total_seconds() / 86400.0
    phase = (days % SYNODIC_MONTH_DAYS) / SYNODIC_MONTH_DAYS  # 0..1
    illumination = (1 - math.cos(2 * math.pi * phase)) / 2
    # Name from phase
    if phase < 0.03 or phase > 0.97:
        name = "New"
    elif phase < 0.22:
        name = "Waxing crescent"
    elif phase < 0.28:
        name = "First quarter"
    elif phase < 0.47:
        name = "Waxing gibbous"
    elif phase < 0.53:
        name = "Full"
    elif phase < 0.72:
        name = "Waning gibbous"
    elif phase < 0.78:
        name = "Last quarter"
    else:
        name = "Waning crescent"
    return {
        "phase": round(phase, 3),
        "illumination_pct": round(illumination * 100, 1),
        "name": name,
    }


def _sunrise_sunset(lat: float, lon: float, day: date) -> dict[str, Any]:
    """NOAA approximation (good to a few seconds). Returns ISO times in UTC."""
    # Day of year
    n = day.timetuple().tm_yday
    # Approximate solar declination
    g = 2 * math.pi / 365 * (n - 1)
    decl = (
        0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g)
    )
    # Equation of time (minutes)
    eqt = 229.18 * (
        0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g)
    )
    # Hour angle for sunrise/sunset (zenith = 90.833° for refraction)
    cos_h = (
        math.cos(math.radians(90.833))
        - math.sin(math.radians(lat)) * math.sin(decl)
    ) / (math.cos(math.radians(lat)) * math.cos(decl))
    if cos_h > 1:
        return {"sunrise": None, "sunset": None, "polar": "night"}
    if cos_h < -1:
        return {"sunrise": None, "sunset": None, "polar": "day"}
    H = math.degrees(math.acos(cos_h))  # degrees
    # Solar noon (UT, minutes after 00:00)
    solar_noon = 720 - 4 * lon - eqt
    sunrise = solar_noon - 4 * H
    sunset = solar_noon + 4 * H

    def _to_iso(minutes: float) -> str:
        dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + \
             timedelta(minutes=minutes)
        return dt.isoformat()

    return {
        "sunrise": _to_iso(sunrise),
        "sunset": _to_iso(sunset),
        "solar_noon": _to_iso(solar_noon),
        "daylight_hours": round((sunset - sunrise) / 60.0, 2),
    }


class SunMoonWidget(Widget):
    id = "sun_moon"
    kind = "sun_moon"
    name = "Sun & moon"
    description = (
        "Sunrise / sunset / solar noon plus moon phase + illumination. "
        "Local computation, no external API. Pair with tides for "
        "fishing-friendly windows."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Outdoor"
    default_position = 30

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
        now = datetime.now(timezone.utc)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        return {
            "fetched_at": now.isoformat(),
            "lat": lat, "lon": lon,
            "moon": _moon_phase(now),
            "today": {"date": today.isoformat(), **_sunrise_sunset(lat, lon, today)},
            "tomorrow": {"date": tomorrow.isoformat(), **_sunrise_sunset(lat, lon, tomorrow)},
        }
