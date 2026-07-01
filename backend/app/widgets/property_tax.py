"""San Felipe property tax (predial) countdown.

Payment portal: http://pagoenlinea.sanfelipe.gob.mx — Mexican predial is
typically due in the first quarter of the year, with early-bird
discounts in January/February. April is a safe outer deadline.

This widget doesn't scrape the portal (it needs your CURP + cadastral
number to look up any real state); it just tracks a configurable due
date + a "paid this year?" flag so you can dismiss the reminder once
you've paid.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


class PropertyTaxWidget(Widget):
    id = "property_tax"
    kind = "property_tax"
    name = "Property tax (predial)"
    description = (
        "San Felipe predial countdown. Click to open the payment portal. "
        "Toggle 'paid this year' after you've paid to silence the "
        "reminder until next year."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Community"
    default_position = 100

    config_schema = {
        "type": "object",
        "properties": {
            "cadastral_number": {"type": "string"},
            "due_month": {"type": "integer", "minimum": 1, "maximum": 12},
            "due_day":   {"type": "integer", "minimum": 1, "maximum": 31},
            "payment_url": {"type": "string", "format": "uri"},
            "paid_year": {"type": ["integer", "null"]},
            "notes": {"type": "string"},
        },
    }
    default_config = {
        "cadastral_number": "49604007",
        "due_month": 4,
        "due_day": 1,
        "payment_url": "http://pagoenlinea.sanfelipe.gob.mx",
        "paid_year": None,
        "notes": (
            "Early-bird discounts usually available in January (10%) and "
            "February (5%). Bring your cadastral number and CURP."
        ),
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        today = date.today()
        due_month = int(config.get("due_month", 4))
        due_day = int(config.get("due_day", 1))
        paid_year = config.get("paid_year")

        try:
            due_this_year = date(today.year, due_month, due_day)
        except ValueError:
            due_this_year = date(today.year, due_month, 1)
        if due_this_year < today:
            due_next = date(today.year + 1, due_month, due_day)
        else:
            due_next = due_this_year

        overdue = today > due_this_year and paid_year != today.year
        paid = paid_year == today.year

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "cadastral_number": config.get("cadastral_number"),
            "payment_url": config.get("payment_url"),
            "due_this_year": due_this_year.isoformat(),
            "due_next": due_next.isoformat(),
            "days_until_due": (due_next - today).days,
            "paid_this_year": paid,
            "overdue": overdue,
            "notes": config.get("notes", ""),
        }
