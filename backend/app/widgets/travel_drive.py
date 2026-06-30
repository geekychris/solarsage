"""Drive-time widget — OSRM public router.

Computes drive time + distance between configured points. Defaults: San
Felipe ↔ Calexico West POE. Combines with the border widget by reading
its cached state and reporting "drive + border = total trip".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

OSRM_URL = (
    "https://router.project-osrm.org/route/v1/driving/"
    "{from_lon},{from_lat};{to_lon},{to_lat}"
    "?overview=false&alternatives=false"
)


class DriveTimeWidget(Widget):
    id = "drive_time"
    kind = "drive_time"
    name = "Drive times"
    description = (
        "Driving distance and time between configured points (OSRM public "
        "router). Default: San Felipe ↔ Calexico West POE. The widget "
        "doesn't model live traffic, so this is your free-flow baseline."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Travel"
    default_position = 30

    config_schema = {
        "type": "object",
        "properties": {
            "routes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "label", "from", "to"],
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "from": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "number"},
                                "lon": {"type": "number"},
                            },
                        },
                        "to": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "number"},
                                "lon": {"type": "number"},
                            },
                        },
                    },
                },
            },
        },
    }
    default_config = {
        "routes": [
            {
                "id": "sf_to_calexico_w",
                "label": "San Felipe → Calexico West",
                "from": {"lat": 31.025, "lon": -114.838},
                "to":   {"lat": 32.6675, "lon": -115.4994},
            },
            {
                "id": "sf_to_mexicali",
                "label": "San Felipe → Mexicali",
                "from": {"lat": 31.025, "lon": -114.838},
                "to":   {"lat": 32.624, "lon": -115.453},
            },
        ]
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        routes = config.get("routes") or []
        results = []
        async with aiohttp.ClientSession() as http:
            for r in routes:
                url = OSRM_URL.format(
                    from_lon=r["from"]["lon"], from_lat=r["from"]["lat"],
                    to_lon=r["to"]["lon"], to_lat=r["to"]["lat"],
                )
                try:
                    async with http.get(
                        url, timeout=30,
                        headers={"User-Agent": "SolarSage/1.0 (drive-time)"},
                    ) as resp:
                        resp.raise_for_status()
                        payload = await resp.json()
                    rt = (payload.get("routes") or [{}])[0]
                    results.append({
                        "id": r["id"],
                        "label": r["label"],
                        "distance_km": round(float(rt.get("distance", 0)) / 1000, 1),
                        "duration_min": round(float(rt.get("duration", 0)) / 60, 1),
                        "ok": True,
                    })
                except Exception as exc:  # noqa: BLE001
                    results.append({
                        "id": r["id"], "label": r["label"],
                        "error": str(exc), "ok": False,
                    })
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "routes": results,
            "note": "Times are free-flow estimates — combine with /api/widgets/border for total trip.",
        }
