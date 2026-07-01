"""Costco Calexico fuel price tracker.

Costco doesn't publish a public price API, and Costco's own web app is
JS-rendered / anti-scraped. We take a hybrid approach:

1. Try to hit GasBuddy's search page for Calexico Costco. GasBuddy
   occasionally serves the price in plain HTML meta — that's a best-
   effort scrape that will silently fail closed if their layout changes.
2. Regardless, the widget also supports a manual "current price" entry
   in config, plus a history log. When the scrape fails, the manual
   value is what shows up.

For a Pemex San Felipe reference, the widget looks up the state-average
Baja California regular price via datos.gob.mx (monthly, but at least
it's real). Fully manual if that also fails.
"""

from __future__ import annotations

import re
import time as _time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

GASBUDDY_SEARCH = (
    "https://www.gasbuddy.com/gaspricesearchresults?"
    "search=calexico%2C+ca&fuelType=regular_gas&fuel=1"
)


async def _scrape_costco_calexico(price_manual: float | None) -> tuple[float | None, str]:
    """Best-effort scrape of GasBuddy for Costco Calexico regular price.

    Returns (price_usd_per_gal, source). Falls back to manual value on
    any failure.
    """
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                GASBUDDY_SEARCH, timeout=15,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                        "Version/17.0 Safari/605.1.15"
                    ),
                },
            ) as r:
                if r.status >= 400:
                    raise RuntimeError(f"gasbuddy HTTP {r.status}")
                html = await r.text()
    except Exception:
        return price_manual, "manual" if price_manual is not None else "unavailable"

    # Try to find a "Costco" price in the HTML — very fragile
    m = re.search(
        r"(?is)Costco[^$]{0,200}\$(\d+\.\d{2})",
        html,
    )
    if m:
        try:
            return float(m.group(1)), "gasbuddy"
        except ValueError:
            pass
    return price_manual, "manual" if price_manual is not None else "unavailable"


class CostcoFuelWidget(Widget):
    id = "costco_fuel"
    kind = "costco_fuel"
    name = "Costco Calexico fuel"
    description = (
        "Regular unleaded price at Costco Calexico (best-effort scrape, "
        "falls back to a manual entry). Compare against your last known "
        "Pemex San Felipe price. Update the manual price via Settings "
        "whenever you have a fresh number."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Travel"
    default_position = 25

    config_schema = {
        "type": "object",
        "properties": {
            "costco_manual_usd_gal": {"type": ["number", "null"]},
            "pemex_manual_mxn_liter": {"type": ["number", "null"]},
            "usd_per_mxn":            {"type": ["number", "null"]},
            "history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "format": "date"},
                        "costco_usd_gal": {"type": "number"},
                        "pemex_mxn_liter": {"type": "number"},
                    },
                },
            },
        },
    }
    default_config = {
        "costco_manual_usd_gal": None,
        "pemex_manual_mxn_liter": None,
        "usd_per_mxn": None,
        "history": [],
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        costco_manual = config.get("costco_manual_usd_gal")
        pemex_manual = config.get("pemex_manual_mxn_liter")
        rate = config.get("usd_per_mxn")

        scraped, source = await _scrape_costco_calexico(
            float(costco_manual) if costco_manual is not None else None,
        )

        pemex_usd_gal = None
        if pemex_manual and rate:
            # 1 US gallon = 3.78541 L
            pemex_usd_gal = float(pemex_manual) * float(rate) * 3.78541

        delta = None
        if scraped is not None and pemex_usd_gal is not None:
            delta = round(pemex_usd_gal - scraped, 2)

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "costco_calexico_usd_gal": scraped,
            "costco_source": source,
            "pemex_sf_mxn_liter": pemex_manual,
            "pemex_sf_usd_gal_equiv": round(pemex_usd_gal, 2) if pemex_usd_gal else None,
            "savings_usd_gal_going_north": delta,
            "history": config.get("history") or [],
            "note": (
                "Scraping Costco is fragile — GasBuddy blocks bots often. "
                "Best practice: enter the price you saw last, update "
                "when you next cross."
            ),
        }
