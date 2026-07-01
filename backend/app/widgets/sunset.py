"""Sunset countdown widget — minutes to sunset + civil dusk today.

Refreshes once every couple of hours; the frontend re-runs the
countdown from the ISO timestamps every second so the numbers tick
live without touching the backend.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from .base import Widget
from .outdoor_sunmoon import _sunrise_sunset


def _civil_dusk_iso(sunset_iso: str, minutes_after: int = 30) -> str:
    dt = datetime.fromisoformat(sunset_iso)
    return (dt + timedelta(minutes=minutes_after)).isoformat()


class SunsetWidget(Widget):
    id = "sunset"
    kind = "sunset"
    name = "Sunset countdown"
    description = (
        "Minutes to sunset and civil dusk for the configured location, "
        "with a highlighted 'golden 20' window (20 min before sunset). "
        "The frontend counts down live; the backend refreshes twice a day."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Outdoor"
    default_position = 25

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at":     {"type": "string", "format": "date-time"},
            "sunrise":        {"type": ["string", "null"], "format": "date-time"},
            "sunset":         {"type": ["string", "null"], "format": "date-time"},
            "civil_dusk":     {"type": ["string", "null"], "format": "date-time"},
            "golden_start":   {"type": ["string", "null"], "format": "date-time"},
            "next_sunrise":   {"type": ["string", "null"], "format": "date-time"},
            "next_sunset":    {"type": ["string", "null"], "format": "date-time"},
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "golden_minutes": {"type": "integer"},
            "civil_dusk_after_sunset_minutes": {"type": "integer"},
        },
    }
    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "golden_minutes": 20,
        "civil_dusk_after_sunset_minutes": 30,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        golden_min = int(config.get("golden_minutes", 20))
        civil_delta = int(config.get("civil_dusk_after_sunset_minutes", 30))

        now = datetime.now(timezone.utc)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        today_ss = _sunrise_sunset(lat, lon, today)
        tomorrow_ss = _sunrise_sunset(lat, lon, tomorrow)

        sunset = today_ss.get("sunset")
        golden_start = None
        civil_dusk = None
        if sunset:
            ss_dt = datetime.fromisoformat(sunset)
            golden_start = (ss_dt - timedelta(minutes=golden_min)).isoformat()
            civil_dusk = _civil_dusk_iso(sunset, civil_delta)

        return {
            "fetched_at":   now.isoformat(),
            "lat": lat, "lon": lon,
            "sunrise":      today_ss.get("sunrise"),
            "sunset":       sunset,
            "civil_dusk":   civil_dusk,
            "golden_start": golden_start,
            "golden_minutes": golden_min,
            "next_sunrise": tomorrow_ss.get("sunrise"),
            "next_sunset":  tomorrow_ss.get("sunset"),
        }
