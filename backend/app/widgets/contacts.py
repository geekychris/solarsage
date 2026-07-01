"""Contact list widget — simple user-editable directory.

Data lives in the widget's config (``contacts`` array). Add / edit /
delete via Settings (or via PUT /api/widgets/contacts/config from a
script).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import Widget


class ContactsWidget(Widget):
    id = "contacts"
    kind = "contacts"
    name = "Contacts"
    description = (
        "Your address book of people you reach for down here + up north. "
        "Fields: name, phone, email, location tag (US/MX), notes. Search "
        "the list from the card."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Community"
    default_position = 200
    sheets_tab = "Contacts"
    sheets_list_field = "contacts"
    sheets_field_order = ["name", "phone", "email", "location", "tags", "notes"]

    config_schema = {
        "type": "object",
        "properties": {
            "contacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name":     {"type": "string"},
                        "phone":    {"type": "string"},
                        "email":    {"type": "string"},
                        "location": {"enum": ["mx", "us", "other"]},
                        "tags":     {"type": "array", "items": {"type": "string"}},
                        "notes":    {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {
        "contacts": [
            {"name": "HOA Activities Director (David Alva)",
             "phone": "+52 686 149 0379",
             "email": "david.alva@doradoranch.com.mx",
             "location": "mx", "tags": ["hoa"], "notes": ""},
            {"name": "EDR Security (emergency)",
             "phone": "+52 686 576 0587",
             "email": "", "location": "mx", "tags": ["emergency"],
             "notes": "Alt: 686 569 6441"},
            {"name": "Pavilion Restaurant",
             "phone": "+52 686 576 0519",
             "email": "", "location": "mx",
             "tags": ["hoa", "food"], "notes": ""},
            {"name": "Las Caras de México Golf",
             "phone": "+52 686 576 0517",
             "email": "golf@doradoranch.com.mx",
             "location": "mx", "tags": ["hoa", "golf"], "notes": ""},
        ]
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "contacts": config.get("contacts") or [],
        }
