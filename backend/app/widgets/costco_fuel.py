"""Fuel price tracker — Costco Calexico + Pemex San Felipe + regional refs.

Reachable / real sources from this pi:

1. **EIA California retail weekly** — US EIA v2 API, ``$/gal`` for regular.
   Works with a free API key (fallback to ``DEMO_KEY``). This is the
   closest public "Imperial Valley area" number we can get; Imperial
   County isn't broken out but the CA average is real and updated weekly.

2. **Pemex San Felipe** — manual entry. The Mexican government
   ``datos.gob.mx`` API is network-blocked from this pi (HTTP 000), so
   we surface a launcher URL and rely on the user typing the pump price
   in occasionally.

3. **Costco Calexico** — manual entry. Neither Costco nor GasBuddy
   serve prices reliably to scrapers.

For each manual entry we track ``updated_at`` and flag it stale if it
hasn't been touched in >14 days.
"""

from __future__ import annotations

import os
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

EIA_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
STALE_DAYS = 14


async def _fetch_eia_california_regular(api_key: str) -> tuple[float | None, str | None]:
    """Return (usd_per_gal, iso_date) of the most recent CA retail regular
    weekly avg. Returns (None, None) on any failure."""
    params = {
        "frequency": "weekly",
        "facets[duoarea][]": "SCA",
        "facets[product][]": "EPMR",
        "data[0]": "value",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": "1",
        "api_key": api_key,
    }
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(EIA_URL, params=params, timeout=15) as r:
                if r.status >= 400:
                    return None, None
                payload = await r.json()
    except Exception:
        return None, None
    try:
        row = payload["response"]["data"][0]
        return float(row["value"]), str(row["period"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None, None


def _staleness(updated_at: str | None) -> dict[str, Any] | None:
    if not updated_at:
        return None
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    return {
        "updated_at": updated_at,
        "age_days": round(days, 1),
        "stale": days > STALE_DAYS,
    }


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
    name = "Fuel prices"
    description = (
        "Regular unleaded — real California retail weekly average from "
        "the US EIA API, plus manual entries for Costco Calexico and "
        "Pemex San Felipe. Manual entries age out after 14 days so you "
        "know when to refresh. Compare cross-border to plan fills."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Travel"
    default_position = 25

    config_schema = {
        "type": "object",
        "properties": {
            "costco_manual_usd_gal": {"type": ["number", "null"]},
            "costco_updated_at":     {"type": ["string", "null"]},
            "pemex_manual_mxn_liter": {"type": ["number", "null"]},
            "pemex_updated_at":       {"type": ["string", "null"]},
            "usd_per_mxn":            {"type": ["number", "null"]},
            "eia_api_key":            {"type": ["string", "null"],
                                        "description": "Free key from eia.gov/opendata — falls back to DEMO_KEY"},
            "try_costco_scrape":      {"type": "boolean"},
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
        "costco_updated_at": None,
        "pemex_manual_mxn_liter": None,
        "pemex_updated_at": None,
        "usd_per_mxn": None,
        "eia_api_key": None,
        "try_costco_scrape": False,
        "history": [],
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        costco_manual = config.get("costco_manual_usd_gal")
        pemex_manual = config.get("pemex_manual_mxn_liter")
        rate = config.get("usd_per_mxn")

        # Real: EIA California retail weekly average
        eia_key = (
            config.get("eia_api_key")
            or os.getenv("EIA_API_KEY")
            or "DEMO_KEY"
        )
        ca_avg_usd_gal, ca_avg_date = await _fetch_eia_california_regular(eia_key)

        # Best effort scrape (usually fails — disabled by default)
        scraped, costco_source = (None, "manual")
        if config.get("try_costco_scrape"):
            scraped, costco_source = await _scrape_costco_calexico(
                float(costco_manual) if costco_manual is not None else None,
            )
        costco_val = scraped if scraped is not None else (
            float(costco_manual) if costco_manual is not None else None
        )

        pemex_usd_gal = None
        if pemex_manual and rate:
            # 1 US gallon = 3.78541 L
            pemex_usd_gal = float(pemex_manual) * float(rate) * 3.78541

        delta = None
        if costco_val is not None and pemex_usd_gal is not None:
            delta = round(pemex_usd_gal - costco_val, 2)

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "ca_avg_usd_gal": ca_avg_usd_gal,
            "ca_avg_date": ca_avg_date,
            "ca_avg_source": (
                "eia.gov" if ca_avg_usd_gal is not None else "unavailable"
            ),
            "costco_calexico_usd_gal": costco_val,
            "costco_source": costco_source,
            "costco_staleness": _staleness(config.get("costco_updated_at")),
            "pemex_sf_mxn_liter": pemex_manual,
            "pemex_sf_usd_gal_equiv":
                round(pemex_usd_gal, 2) if pemex_usd_gal else None,
            "pemex_staleness": _staleness(config.get("pemex_updated_at")),
            "usd_per_mxn": rate,
            "savings_usd_gal_going_north": delta,
            "history": config.get("history") or [],
            "sources": {
                "ca_avg": "US EIA API v2 — California retail weekly regular",
                "costco": "Manual (Costco / GasBuddy don't serve prices to scrapers)",
                "pemex":  "Manual (Mexican gov APIs blocked from this network)",
            },
        }
