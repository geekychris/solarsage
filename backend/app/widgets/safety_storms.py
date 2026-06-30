"""Tropical-storm widget — NHC current storms feed.

The NHC publishes `CurrentStorms.json` covering active tropical cyclones
in the Atlantic (AL), Eastern Pacific (EP) and Central Pacific (CP)
basins. We default to EP since that's what threatens the Gulf of
California / Baja peninsula in summer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

NHC_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"


class StormsWidget(Widget):
    id = "storms"
    kind = "storms"
    name = "Tropical storms"
    description = (
        "Active tropical cyclones (NHC). Filters to the basins configured; "
        "Eastern Pacific (EP) is the one to watch for Sea of Cortez impact."
    )
    refresh_seconds = 30 * 60
    default_tab = "Safety"
    default_position = 20

    config_schema = {
        "type": "object",
        "properties": {
            "basins": {
                "type": "array",
                "items": {"enum": ["AL", "EP", "CP"]},
            },
        },
    }
    default_config = {"basins": ["EP"]}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        basins = set(config.get("basins") or ["EP"])
        async with aiohttp.ClientSession() as http:
            async with http.get(
                NHC_URL, timeout=30,
                headers={"User-Agent": "SolarSage/1.0 (storms widget)"},
            ) as r:
                r.raise_for_status()
                payload = await r.json()

        active = []
        for st in payload.get("activeStorms") or []:
            basin = (st.get("binNumber") or "")[:2].upper() or st.get("basin")
            if basins and basin not in basins:
                continue
            active.append({
                "id": st.get("id"),
                "name": st.get("name"),
                "class": st.get("classification"),
                "intensity": st.get("intensity"),  # knots
                "pressure": st.get("pressure"),    # mb
                "lat": st.get("latitudeNumeric"),
                "lon": st.get("longitudeNumeric"),
                "movement": st.get("movement"),
                "last_update": st.get("lastUpdate"),
                "binNumber": st.get("binNumber"),
                "advisoryNumber": st.get("advisoryNumber"),
                "publicAdvisory": (st.get("publicAdvisory") or {}).get("url"),
                "trackCone": (st.get("trackCone") or {}).get("kmzFile"),
            })
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "basins_watched": sorted(basins),
            "active_count": len(active),
            "active_storms": active,
        }
