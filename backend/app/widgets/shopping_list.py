"""Shopping list widget — bring-back-from-US checklist.

Add items you need to buy in the US and bring down next time. Data
stored in widget config so it's fully user-editable via Settings.
Google Sheets sync is not wired yet — see backlog.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import Widget


class ShoppingListWidget(Widget):
    id = "shopping_list"
    kind = "shopping_list"
    name = "Shopping list (bring down)"
    description = (
        "Items to buy in the US on your next Calexico Costco run. Checked "
        "items stick around until you clear them so you can un-check for "
        "next trip. Sheets sync is on the backlog — export/import via "
        "the config JSON in the meantime."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Travel"
    default_position = 100
    sheets_tab = "Shopping"
    sheets_list_field = "items"
    sheets_field_order = ["text", "category", "checked", "notes"]

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
                        "category": {"type": "string"},
                        "checked":  {"type": "boolean"},
                        "notes":    {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {
        "items": [
            {"text": "Costco vitamins (Kirkland)", "category": "Health",
             "checked": False, "notes": ""},
            {"text": "Amazon delivery boxes", "category": "Amazon",
             "checked": False, "notes": ""},
        ]
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": config.get("items") or [],
        }
