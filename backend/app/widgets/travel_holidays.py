"""Mexican federal holidays — date.nager.at public API (no key)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

NAGER_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"


class HolidaysWidget(Widget):
    id = "holidays"
    kind = "holidays"
    name = "Mexican holidays"
    description = (
        "Federal public holidays for the configured country (default MX). "
        "Highlights the next holiday and how many days away it is — handy "
        "for planning bank / Pemex / government-office closures."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Travel"
    default_position = 40

    config_schema = {
        "type": "object",
        "properties": {
            "country": {"type": "string", "description": "ISO-3166 alpha-2"},
        },
    }
    default_config = {"country": "MX"}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        country = str(config.get("country", "MX")).upper()
        today = date.today()
        years = [today.year, today.year + 1]
        all_holidays: list[dict[str, Any]] = []
        async with aiohttp.ClientSession() as http:
            for y in years:
                url = NAGER_URL.format(year=y, country=country)
                async with http.get(url, timeout=30) as r:
                    r.raise_for_status()
                    items = await r.json()
                for h in items:
                    all_holidays.append({
                        "date": h.get("date"),
                        "name": h.get("name"),
                        "local_name": h.get("localName"),
                        "types": h.get("types") or [],
                    })

        upcoming = sorted(
            (h for h in all_holidays if h["date"] >= today.isoformat()),
            key=lambda h: h["date"],
        )
        next_h = upcoming[0] if upcoming else None
        days_until = None
        if next_h:
            d = date.fromisoformat(next_h["date"])
            days_until = (d - today).days
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "country": country,
            "next": next_h,
            "days_until_next": days_until,
            "upcoming": upcoming[:10],
        }
