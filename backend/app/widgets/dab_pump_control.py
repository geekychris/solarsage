"""DAB e.syMINI water-pump control widget.

Read side: current mode + short countdown (so the toggles reflect
truth without waiting for the stats widget's slower refresh).

Write side: the backend endpoint ``/api/widgets/dab_pump/control``
translates a short ``action`` verb into the right HA service call.
See ``main.py``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget
from .dab_pump import _ha_state, _as_int, _as_float

log = logging.getLogger("eg4.widgets.dab_pump_control")


class DabPumpControlWidget(Widget):
    id = "dab_pump_control"
    kind = "dab_pump_control"
    name = "Water pump — controls"
    description = (
        "Big Sleep-mode + Power-Shower toggles for the DAB e.syMINI. "
        "Also exposes the boost / reduction percentage selectors and "
        "the maintenance pump enable/disable switch."
    )
    refresh_seconds = 30    # short — matters for the toggle state
    default_tab = "House"
    default_position = 11

    ha_entities = [
        # Read-side (mirror mode + countdowns)
        {"key": "sleep_switch_eid",         "label": "Sleep mode enable",
         "domain": "switch", "required": True},
        {"key": "power_shower_select_eid",  "label": "Power Shower command",
         "domain": "select", "required": True},
        {"key": "pump_disable_select_eid",  "label": "Pump enable/disable",
         "domain": "select", "required": False},
        {"key": "power_shower_boost_eid",   "label": "Power Shower boost (%)",
         "domain": "select", "required": False},
        {"key": "sleep_reduction_eid",      "label": "Sleep mode reduction (%)",
         "domain": "select", "required": False},
        {"key": "status_eid",               "label": "Pump status (mirror)",
         "domain": "sensor", "required": False},
        {"key": "power_shower_countdown_eid", "label": "Power Shower countdown",
         "domain": "sensor", "required": False},
        {"key": "sleep_countdown_eid",      "label": "Sleep mode countdown",
         "domain": "sensor", "required": False},
    ]

    config_schema = {
        "type": "object",
        "properties": {k["key"]: {"type": "string"} for k in ha_entities},
    }

    default_config = {
        "sleep_switch_eid":            "switch.esyminiv2_rhjl6_sleepmodeenable",
        "power_shower_select_eid":     "select.esyminiv2_rhjl6_powershowercommand",
        "pump_disable_select_eid":     "select.esyminiv2_rhjl6_pumpdisable",
        "power_shower_boost_eid":      "select.esyminiv2_rhjl6_powershowerboost",
        "sleep_reduction_eid":         "select.esyminiv2_rhjl6_sleepmodereduction",
        "status_eid":                  "sensor.esyminiv2_rhjl6_pumpstatus",
        "power_shower_countdown_eid":  "sensor.esyminiv2_rhjl6_powershowercountdown",
        "sleep_countdown_eid":         "sensor.esyminiv2_rhjl6_sleepmodecountdown",
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            raise RuntimeError("HA_URL + HA_TOKEN not set in backend/.env")

        eids = {k["key"]: (config.get(k["key"]) or "") for k in self.ha_entities}

        async with aiohttp.ClientSession() as http:
            reads = {}
            attrs = {}
            for key, eid in eids.items():
                state, a = await _ha_state(http, ha_url, ha_token, eid)
                reads[key] = state
                attrs[key] = a or {}

        ps_countdown = _as_int(reads.get("power_shower_countdown_eid"))
        sleep_countdown = _as_int(reads.get("sleep_countdown_eid"))
        active_mode = None
        if ps_countdown and ps_countdown > 0:
            active_mode = "power_shower"
        elif sleep_countdown and sleep_countdown > 0:
            active_mode = "sleep"

        def _options(key: str) -> list[str]:
            opts = attrs.get(key, {}).get("options") or []
            # 'Enable/Disable' selects have a '--' idle placeholder we
            # don't want to surface to users as a real choice.
            return [o for o in opts if o and o != "--"]

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status":                reads.get("status_eid"),
            "active_mode":           active_mode,
            "sleep_mode_on":         (reads.get("sleep_switch_eid") == "on"),
            "power_shower_countdown_s": ps_countdown,
            "sleep_countdown_s":     sleep_countdown,
            "power_shower_boost":    reads.get("power_shower_boost_eid"),
            "sleep_reduction":       reads.get("sleep_reduction_eid"),
            "pump_disable_state":    reads.get("pump_disable_select_eid"),
            "options": {
                "power_shower_boost":  _options("power_shower_boost_eid"),
                "sleep_reduction":     _options("sleep_reduction_eid"),
                "pump_disable":        _options("pump_disable_select_eid"),
            },
        }
