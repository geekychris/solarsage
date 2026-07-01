"""Whale-watching season indicator (Sea of Cortez, ~Nov 1 → Apr 30)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


def _in_season(today: date, start_md: tuple[int, int], end_md: tuple[int, int]) -> bool:
    m, d = today.month, today.day
    s = start_md
    e = end_md
    # Season wraps year boundary → in-season if today >= start OR today <= end
    return (m, d) >= s or (m, d) <= e


def _next_boundary(today: date, month: int, day: int) -> date:
    for y in (today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d >= today:
            return d
    return date(today.year + 1, month, day)


class WhaleSeasonWidget(Widget):
    id = "whale_season"
    kind = "whale_season"
    name = "Whale watching"
    description = (
        "Sea of Cortez whale-watching season indicator. Fin, blue, and "
        "gray whales are commonly sighted from November through April."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Outdoor"
    default_position = 40

    config_schema = {
        "type": "object",
        "properties": {
            "start_month": {"type": "integer", "minimum": 1, "maximum": 12},
            "start_day":   {"type": "integer", "minimum": 1, "maximum": 31},
            "end_month":   {"type": "integer", "minimum": 1, "maximum": 12},
            "end_day":     {"type": "integer", "minimum": 1, "maximum": 31},
        },
    }
    default_config = {
        "start_month": 11, "start_day": 1,
        "end_month": 4, "end_day": 30,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        today = date.today()
        start = (int(config.get("start_month", 11)), int(config.get("start_day", 1)))
        end = (int(config.get("end_month", 4)), int(config.get("end_day", 30)))
        active = _in_season(today, start, end)
        next_start = _next_boundary(today, *start)
        next_end = _next_boundary(today, *end)
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "in_season": active,
            "starts_at": next_start.isoformat(),
            "ends_at": next_end.isoformat(),
            "days_until_start": (next_start - today).days,
            "days_until_end": (next_end - today).days,
            "species": [
                "Fin whale (Balaenoptera physalus)",
                "Blue whale (Balaenoptera musculus)",
                "Bryde's whale (Balaenoptera edeni)",
                "Gray whale (Eschrichtius robustus)",
                "Common dolphin",
            ],
        }
