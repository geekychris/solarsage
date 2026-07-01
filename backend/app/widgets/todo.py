"""Todo widget — task list with priority + due date.

Sheets-backed (tab: ``Todo``) so you can edit it from your phone in
the Google Sheets app or from the dashboard's inline UI.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


class TodoWidget(Widget):
    id = "todo"
    kind = "todo"
    name = "Todo"
    description = (
        "General-purpose task list — priority (1=high / 5=low), optional "
        "due date, done flag, notes. Syncs to the Todo tab of your "
        "SolarSage Lists workbook."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Community"
    default_position = 205

    sheets_tab = "Todo"
    sheets_list_field = "items"
    sheets_field_order = ["text", "priority", "due", "done", "notes"]

    config_schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "text":     {"type": "string"},
                        "priority": {"type": ["integer", "null"],
                                     "minimum": 1, "maximum": 5},
                        "due":      {"type": ["string", "null"],
                                     "format": "date"},
                        "done":     {"type": "boolean"},
                        "notes":    {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {"items": []}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        items = list(config.get("items") or [])
        today = date.today().isoformat()
        overdue = sum(
            1 for it in items
            if not it.get("done") and it.get("due") and it["due"] < today
        )
        open_count = sum(1 for it in items if not it.get("done"))
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "stats": {
                "total": len(items),
                "open": open_count,
                "overdue": overdue,
            },
        }
