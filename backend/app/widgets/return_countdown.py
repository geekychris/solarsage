"""Countdown to the next drive back to the US."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


class ReturnCountdownWidget(Widget):
    id = "return_countdown"
    kind = "return_countdown"
    name = "Days until return"
    description = "Countdown to your next drive back north."
    refresh_seconds = 24 * 3600
    default_tab = "Travel"
    default_position = 3

    config_schema = {
        "type": "object",
        "properties": {
            "return_date": {"type": "string", "format": "date"},
            "label": {"type": "string"},
        },
    }
    default_config = {"return_date": None, "label": "Return to US"}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        return_date = config.get("return_date")
        days = None
        if return_date:
            try:
                d = date.fromisoformat(return_date)
                days = (d - date.today()).days
            except ValueError:
                pass
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "return_date": return_date,
            "label": config.get("label") or "Return to US",
            "days_remaining": days,
        }
