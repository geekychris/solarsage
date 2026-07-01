"""Border crossing log.

User-logged history of each crossing (date, direction, port, wait,
notes). Useful for FMM tracking, tax residency, or just knowing
which crossings tend to be worst.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import Widget


class BorderLogWidget(Widget):
    id = "border_log"
    kind = "border_log"
    name = "Border crossing log"
    description = (
        "Log every time you cross the border. Tracks direction (US→MX / "
        "MX→US), which port, actual wait time, and any notes. Handy for "
        "spotting patterns and for FMM / tax-residency records."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Lists"
    default_position = 40
    sheets_tab = "Border Log"
    sheets_list_field = "crossings"
    sheets_field_order = ["date", "direction", "port", "wait_min", "purpose", "notes"]

    config_schema = {
        "type": "object",
        "properties": {
            "crossings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["date"],
                    "properties": {
                        "date":      {"type": "string", "format": "date"},
                        "direction": {"enum": ["us_to_mx", "mx_to_us"]},
                        "port":      {"type": "string"},
                        "wait_min":  {"type": "integer"},
                        "purpose":   {"type": "string"},
                        "notes":     {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {"crossings": []}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        crossings = list(config.get("crossings") or [])
        crossings.sort(key=lambda c: c.get("date") or "", reverse=True)
        # Simple analytics
        this_year = datetime.now(timezone.utc).year
        n_this_year = sum(
            1 for c in crossings
            if (c.get("date") or "").startswith(str(this_year))
        )
        avg_wait = None
        waits = [
            c["wait_min"] for c in crossings
            if isinstance(c.get("wait_min"), (int, float))
        ]
        if waits:
            avg_wait = round(sum(waits) / len(waits), 1)
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "crossings": crossings,
            "stats": {
                "total": len(crossings),
                "this_year": n_this_year,
                "avg_wait_min": avg_wait,
            },
        }
