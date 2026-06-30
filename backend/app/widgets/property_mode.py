"""Property mode widget — single configurable mode flag.

Three modes: ``occupied`` / ``vacant`` / ``arriving``. Other widgets
(pre-cool advisor, excess planner, reminder scheduler) can read this
state and adjust their recommendations (e.g. don't pre-cool an empty
house, don't fire reminders if vacant).

This widget doesn't fetch anything — it just publishes the mode so
both the UI and the LLM (via /api/widgets/property_mode/data) can see
the current state at a glance.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


class PropertyModeWidget(Widget):
    id = "property_mode"
    kind = "property_mode"
    name = "Property mode"
    description = (
        "Who's at the house — Occupied / Vacant / Arriving on a given "
        "date. Other widgets can read this and adjust their behaviour "
        "(e.g. skip pre-cool for a vacant house)."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Solar"
    default_position = 1

    config_schema = {
        "type": "object",
        "properties": {
            "mode": {"enum": ["occupied", "vacant", "arriving"]},
            "arriving_on": {"type": "string", "format": "date"},
            "notes": {"type": "string"},
        },
    }
    default_config = {"mode": "occupied", "arriving_on": None, "notes": ""}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        mode = config.get("mode") or "occupied"
        arriving_on = config.get("arriving_on")
        days_until = None
        if mode == "arriving" and arriving_on:
            try:
                d = date.fromisoformat(arriving_on)
                days_until = (d - date.today()).days
            except ValueError:
                pass
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "arriving_on": arriving_on,
            "days_until_arrival": days_until,
            "notes": config.get("notes") or "",
        }
