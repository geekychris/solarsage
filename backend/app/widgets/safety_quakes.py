"""Earthquake widget — USGS realtime feed.

Filters the global "M2.5+ past day" feed by haversine distance to a
configurable centre point. Default centre is San Felipe; default radius
is 500 km (catches most felt events in the Gulf of California / Baja
peninsula).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

USGS_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class QuakesWidget(Widget):
    id = "quakes"
    kind = "quakes"
    name = "Earthquakes"
    description = (
        "Recent felt earthquakes (M ≥ 2.5) within a configurable radius of "
        "the configured centre. Source: USGS realtime feed."
    )
    refresh_seconds = 10 * 60
    default_tab = "Safety"
    default_position = 10

    config_schema = {
        "type": "object",
        "properties": {
            "lat": {"type": "number"},
            "lon": {"type": "number"},
            "radius_km": {"type": "number"},
            "min_magnitude": {"type": "number"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
        },
    }
    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "radius_km": 500,
        "min_magnitude": 2.5,
        "max_results": 20,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))
        radius = float(config.get("radius_km", 500))
        min_mag = float(config.get("min_magnitude", 2.5))
        max_n = int(config.get("max_results", 20))

        async with aiohttp.ClientSession() as http:
            async with http.get(USGS_URL, timeout=30) as r:
                r.raise_for_status()
                payload = await r.json()

        events = []
        for feat in payload.get("features") or []:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or [None, None, None]
            elon, elat, depth = coords[0], coords[1], coords[2] if len(coords) > 2 else None
            mag = props.get("mag")
            if elon is None or elat is None or mag is None:
                continue
            if mag < min_mag:
                continue
            dist = _haversine_km(lat, lon, float(elat), float(elon))
            if dist > radius:
                continue
            events.append({
                "id": feat.get("id"),
                "magnitude": round(float(mag), 2),
                "place": props.get("place"),
                "time_iso": datetime.fromtimestamp(
                    props.get("time", 0) / 1000.0, tz=timezone.utc,
                ).isoformat(),
                "depth_km": depth,
                "lat": elat,
                "lon": elon,
                "distance_km": round(dist, 1),
                "tsunami": bool(props.get("tsunami")),
                "url": props.get("url"),
            })
        events.sort(key=lambda e: e["time_iso"], reverse=True)
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "centre": {"lat": lat, "lon": lon},
            "radius_km": radius,
            "events": events[:max_n],
        }
