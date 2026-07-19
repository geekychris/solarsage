"""Smart AC plan widget — "what is smart_ac doing, and what's the safety plan?"

Distinct from ``smart_ac_decisions`` (which tails the 5-minute JSONL log
of past ticks). This widget answers a different question: right now,
what's the scheduler intending to do, and if the battery keeps
dropping, what will it do at each threshold?

Everything comes from ``sensor.smart_ac_status`` attributes as emitted
by smart_ac's ``publish_status()``:

- ``intent_summary``           — one-line human sentence
- ``mode``, ``target_on``, ``target_off``, ``enabled``, ``unoccupied``
- ``soc``, ``soc_shed_active_idx``, ``soc_shed_active_step``,
  ``soc_shed_next_action``, ``soc_shed_recovery_at``,
  ``soc_shed_schedule``

Read-only mirror: this widget writes nothing back to HA. If the user
wants to react, they use the AC override chip / kill switch / etc.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

log = logging.getLogger("eg4.widgets.smart_ac_plan")

HA_ENTITY = "sensor.smart_ac_status"


async def _fetch_status(ha_url: str, ha_token: str) -> dict[str, Any] | None:
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"{ha_url}/api/states/{HA_ENTITY}",
                headers={"Authorization": f"Bearer {ha_token}"},
                timeout=10,
            ) as r:
                if r.status != 200:
                    return None
                return await r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s from HA: %s", HA_ENTITY, exc)
        return None


class SmartAcPlanWidget(Widget):
    id = "smart_ac_plan"
    kind = "smart_ac_plan"
    name = "Smart AC plan"
    description = (
        "What smart_ac is doing right now and its SoC-safety plan. Reads "
        "the intent_summary + soc_shed_* attributes from "
        f"``{HA_ENTITY}`` (published by publish_status() in smart_ac.py). "
        "Distinct from the decisions log widget, which shows past ticks."
    )
    refresh_seconds = 60
    default_tab = "Solar"
    default_position = 2

    ha_entities = [
        {"key": "smart_ac_status_entity",
         "label": "smart_ac status sensor",
         "domain": "sensor", "required": False,
         "default": HA_ENTITY},
    ]

    config_schema = {"type": "object", "properties": {}}
    default_config = {}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            return {"note": "HA_URL + HA_TOKEN not configured"}
        entity = await _fetch_status(ha_url, ha_token)
        if entity is None:
            return {"note": f"could not read {HA_ENTITY}"}

        a = entity.get("attributes") or {}
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "mode": entity.get("state"),
            "intent_summary": a.get("intent_summary"),
            "soc": a.get("soc"),
            "enabled": a.get("enabled"),
            "unoccupied": a.get("unoccupied"),
            "target_on": a.get("target_on") or [],
            "target_off": a.get("target_off") or [],
            "last_decision_at": a.get("last_decision_at"),
            "battery_power_w": a.get("battery_power_w"),
            "pv_power_w": a.get("pv_power_w"),
            "load_w": a.get("load_w"),
            "safety": {
                "schedule": a.get("soc_shed_schedule") or [],
                "active_idx": a.get("soc_shed_active_idx"),
                "active_step": a.get("soc_shed_active_step"),
                "next_action": a.get("soc_shed_next_action"),
                "recovery_at": a.get("soc_shed_recovery_at"),
            },
        }
