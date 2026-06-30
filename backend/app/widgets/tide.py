"""Tide table widget — WorldTides API.

Config:
    {"stations": [{"id": "san_felipe", "name": "San Felipe",
                   "lat": 31.025, "lon": -114.838},
                  {"id": "puertecitos", "name": "Puertecitos",
                   "lat": 30.351, "lon": -114.642}],
     "days": 7}

Data:
    {"fetched_at": <iso8601>,
     "stations": [
       {"id": "san_felipe", "name": "San Felipe",
        "extremes": [
           {"dt": <unix>, "iso": "2026-06-30T03:14:00Z",
            "height_m": 1.42, "type": "High"},
           …
        ]},
        …
     ]}

Requires env var ``WORLDTIDES_API_KEY``. Without one the widget reports an
error and the UI shows a "configure key" hint.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

WORLDTIDES_URL = "https://www.worldtides.info/api/v3"


class TideWidget(Widget):
    id = "tides"
    kind = "tides"
    name = "Tide tables"
    description = (
        "High/low tide predictions for configured stations on the Gulf of "
        "California (Sea of Cortez). Data from worldtides.info."
    )
    refresh_seconds = 6 * 3600  # 4× a day; one credit per fetch per station

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at": {"type": "string", "format": "date-time"},
            "stations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "extremes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "dt": {"type": "integer", "description": "unix seconds"},
                                    "iso": {"type": "string", "format": "date-time"},
                                    "height_m": {"type": "number"},
                                    "type": {"enum": ["High", "Low"]},
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": 14},
            "stations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "name", "lat", "lon"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                    },
                },
            },
        },
    }

    default_config = {
        "days": 7,
        "stations": [
            {"id": "san_felipe", "name": "San Felipe",
             "lat": 31.025, "lon": -114.838},
            {"id": "puertecitos", "name": "Puertecitos",
             "lat": 30.351, "lon": -114.642},
        ],
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        api_key = os.getenv("WORLDTIDES_API_KEY")
        if not api_key:
            raise RuntimeError(
                "WORLDTIDES_API_KEY not set — sign up at worldtides.info "
                "and add the key to backend/.env"
            )

        days = int(config.get("days", 7))
        stations = config.get("stations") or []
        today = datetime.now(timezone.utc).date().isoformat()

        results: list[dict[str, Any]] = []
        async with aiohttp.ClientSession() as http:
            for st in stations:
                params = {
                    "extremes": "",
                    "lat": st["lat"],
                    "lon": st["lon"],
                    "key": api_key,
                    "date": today,
                    "days": days,
                }
                async with http.get(WORLDTIDES_URL, params=params, timeout=30) as r:
                    payload = await r.json(content_type=None)
                if payload.get("status") not in (200, None):
                    raise RuntimeError(
                        f"WorldTides {payload.get('status')}: "
                        f"{payload.get('error') or payload}"
                    )
                extremes = []
                for e in payload.get("extremes") or []:
                    extremes.append({
                        "dt": int(e["dt"]),
                        "iso": e.get("date"),
                        "height_m": round(float(e["height"]), 3),
                        "type": e.get("type"),
                    })
                results.append({
                    "id": st["id"],
                    "name": st["name"],
                    "lat": st["lat"],
                    "lon": st["lon"],
                    "extremes": extremes,
                })

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "stations": results,
        }
