"""Property mode widget — house-level occupancy.

**Home Assistant is the source of truth.** The one entity that matters
is ``input_boolean.house_unoccupied`` — the smart_ac scheduler reads it
to decide whether to run normally or in bake-mitigation mode (only
enough AC — living room being the priority — to keep the house from
overheating while nobody's home).

This widget mirrors that HA boolean and lets the user flip it from the
dashboard. Two states:

* **Occupied** — HA ``house_unoccupied`` = off. Normal AC operation.
* **Unoccupied** — HA ``house_unoccupied`` = on. Bake-mitigation mode.

Fetch reads HA every refresh so a flip from anywhere (Telegram, HA UI,
automation) shows up here. The toggle endpoint is
``POST /api/property_mode/set`` (in main.py) which calls HA's service
API and returns the new state.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

log = logging.getLogger("eg4.widgets.property_mode")

HA_ENTITY = "input_boolean.house_unoccupied"


async def read_ha_unoccupied() -> bool | None:
    """Return True if HA says the house is unoccupied, False if occupied,
    None if HA is unavailable / not configured."""
    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        return None
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"{ha_url}/api/states/{HA_ENTITY}",
                headers={"Authorization": f"Bearer {ha_token}"},
                timeout=10,
            ) as r:
                if r.status != 200:
                    return None
                d = await r.json()
                return str(d.get("state") or "").lower() == "on"
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s from HA: %s", HA_ENTITY, exc)
        return None


async def set_ha_unoccupied(unoccupied: bool) -> tuple[bool, str]:
    """Flip the HA input_boolean. Returns (ok, detail)."""
    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        return False, "HA_URL + HA_TOKEN not configured"
    action = "turn_on" if unoccupied else "turn_off"
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{ha_url}/api/services/input_boolean/{action}",
                json={"entity_id": HA_ENTITY},
                headers={
                    "Authorization": f"Bearer {ha_token}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            ) as r:
                if r.status >= 400:
                    text = (await r.text())[:200]
                    return False, f"HA {action} → {r.status}: {text}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {exc}"
    return True, f"HA {action} ok"


class PropertyModeWidget(Widget):
    id = "property_mode"
    kind = "property_mode"
    name = "House occupancy"
    description = (
        "House occupancy — Occupied / Unoccupied. When Unoccupied the "
        "smart_ac scheduler runs in bake-mitigation mode (living room "
        f"prioritized). Mirrors HA's ``{HA_ENTITY}`` — HA is the "
        "source of truth."
    )
    refresh_seconds = 5 * 60
    default_tab = "Solar"
    default_position = 1

    ha_entities = [
        {"key": "house_unoccupied_entity",
         "label": "house_unoccupied input_boolean",
         "domain": "input_boolean", "required": False,
         "default": HA_ENTITY},
    ]

    # No user-editable config anymore — HA is the source of truth. The
    # config schema stays empty so the Settings drawer doesn't offer
    # stale fields.
    config_schema = {"type": "object", "properties": {}}
    default_config = {}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_unoccupied = await read_ha_unoccupied()
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ha_entity": HA_ENTITY,
            "ha_unoccupied": ha_unoccupied,
            "occupied": (not ha_unoccupied) if ha_unoccupied is not None else None,
            "ha_ui_url": ha_url or None,
            # Deep-link to this specific entity's page so clicking the
            # link drops the user right onto the toggle in HA — useful
            # for adjusting occupancy automations that pair with it.
            "ha_entity_url": (
                f"{ha_url}/config/helpers/edit/{HA_ENTITY}" if ha_url else None
            ),
        }
