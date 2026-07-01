"""Water-tank widget — reads a Home Assistant depth sensor, projects
when the tank will need to be refilled, and exposes a percent-full
figure the announcements framework uses to fire low-water warnings.

Config assumes an ultrasonic depth sensor reporting in feet (which is
what pi-sf's ``sensor.water_depth_sensor_distance`` reports). ``full_ft``
is the depth at 100% full; ``empty_ft`` is the depth at 0%. When
``ha_entity_id_max_7d`` is set the widget uses the 7-day maximum reading
to estimate consumption rate and days-remaining.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

log = logging.getLogger("eg4.widgets.water_tank")


async def _ha_state(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str, entity_id: str,
) -> tuple[float | None, dict | None]:
    """Return (float(state), attributes) or (None, None) on any error."""
    try:
        async with http.get(
            f"{ha_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=10,
        ) as r:
            if r.status != 200:
                return None, None
            payload = await r.json()
    except Exception:
        return None, None
    try:
        return float(payload.get("state")), (payload.get("attributes") or {})
    except (TypeError, ValueError):
        return None, (payload.get("attributes") or {})


class WaterTankWidget(Widget):
    id = "water_tank"
    kind = "water_tank"
    name = "Water tank"
    description = (
        "Cistern / tinaco level from a Home Assistant ultrasonic depth "
        "sensor. Shows percent full, gallons remaining (if configured), "
        "days-remaining projection from the 7-day trend, and fires "
        "configurable low-water announcements."
    )
    refresh_seconds = 5 * 60
    default_tab = "Local"
    default_position = 15

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at":     {"type": "string", "format": "date-time"},
            "depth_ft":       {"type": "number"},
            "full_ft":        {"type": "number"},
            "empty_ft":       {"type": "number"},
            "percent":        {"type": "number"},
            "gallons":        {"type": "number"},
            "capacity_gal":   {"type": "number"},
            "days_remaining": {"type": ["number", "null"]},
            "rate_ft_per_day": {"type": ["number", "null"]},
            "trend": {
                "type": "object",
                "properties": {
                    "max_24h_ft": {"type": ["number", "null"]},
                    "max_3d_ft":  {"type": ["number", "null"]},
                    "max_7d_ft":  {"type": ["number", "null"]},
                },
            },
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "ha_entity_id":         {"type": "string"},
            "ha_entity_id_max_24h": {"type": "string"},
            "ha_entity_id_max_7d":  {"type": "string"},
            "full_ft":     {"type": "number"},
            "empty_ft":    {"type": "number"},
            "capacity_gal": {"type": "number"},
        },
    }

    default_config = {
        "ha_entity_id":         "sensor.water_depth_sensor_distance",
        "ha_entity_id_max_24h": "sensor.front_of_house_water_depth_sensor_water_depth_max_24h",
        "ha_entity_id_max_7d":  "sensor.front_of_house_water_depth_sensor_water_depth_max_7d",
        "full_ft":  6.0,
        "empty_ft": 0.0,
        # Tank geometry: 357 US gallons per foot of depth is what the HA
        # /water command uses for the SF cistern. Overrides capacity_gal
        # when set — we derive capacity + current gallons from geometry.
        "gallons_per_ft": 357,
        # Legacy: static capacity_gal. Ignored when gallons_per_ft>0.
        "capacity_gal": 0,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            raise RuntimeError("HA_URL + HA_TOKEN not set in backend/.env")

        eid = config.get("ha_entity_id") or ""
        if not eid:
            raise RuntimeError("water_tank: ha_entity_id not configured")

        full_ft = float(config.get("full_ft") or 0)
        empty_ft = float(config.get("empty_ft") or 0)
        span = full_ft - empty_ft
        capacity_gal = float(config.get("capacity_gal") or 0)

        async with aiohttp.ClientSession() as http:
            depth, _ = await _ha_state(http, ha_url, ha_token, eid)
            max_24h, _ = await _ha_state(
                http, ha_url, ha_token,
                config.get("ha_entity_id_max_24h") or "",
            ) if config.get("ha_entity_id_max_24h") else (None, None)
            max_7d, _ = await _ha_state(
                http, ha_url, ha_token,
                config.get("ha_entity_id_max_7d") or "",
            ) if config.get("ha_entity_id_max_7d") else (None, None)

        if depth is None:
            raise RuntimeError(f"water_tank: {eid} returned no reading")

        percent = None
        if span > 0:
            percent = max(0.0, min(100.0, (depth - empty_ft) / span * 100))

        gal_per_ft = float(config.get("gallons_per_ft") or 0)
        gallons = None
        capacity_gal_out = None
        if gal_per_ft > 0:
            capacity_gal_out = round(gal_per_ft * span)
            gallons = round(gal_per_ft * max(0.0, depth - empty_ft))
        elif percent is not None and capacity_gal > 0:
            capacity_gal_out = capacity_gal
            gallons = round(capacity_gal * percent / 100)

        # Days-remaining projection: use 7-day max as recent full-mark.
        # Rate = (max_7d - current) / 7 days, in ft/day.
        rate_ft_per_day = None
        gal_per_day = None
        days_remaining = None
        if max_7d is not None and max_7d > depth and empty_ft is not None:
            drop = max_7d - depth
            rate_ft_per_day = round(drop / 7, 4)
            # Time to reach empty_ft at current rate
            if rate_ft_per_day > 0:
                days_remaining = round((depth - empty_ft) / rate_ft_per_day, 1)
                if gal_per_ft > 0:
                    gal_per_day = round(rate_ft_per_day * gal_per_ft)

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "entity_id": eid,
            "depth_ft": round(depth, 2),
            "full_ft": full_ft,
            "empty_ft": empty_ft,
            "percent": None if percent is None else round(percent, 1),
            "gallons": gallons,
            "capacity_gal": capacity_gal_out,
            "gallons_per_ft": gal_per_ft or None,
            "days_remaining": days_remaining,
            "rate_ft_per_day": rate_ft_per_day,
            "gal_per_day": gal_per_day,
            "trend": {
                "max_24h_ft": None if max_24h is None else round(max_24h, 2),
                "max_3d_ft":  None,   # not fetched (HA has it but rarely needed)
                "max_7d_ft":  None if max_7d is None else round(max_7d, 2),
            },
        }
