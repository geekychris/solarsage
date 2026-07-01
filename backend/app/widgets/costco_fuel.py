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

import math
import os
import re
import time as _time
import xml.etree.ElementTree as ET
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

# Mexican gov (CRE) public gas-price feeds — served from Azure, reachable
# from the pi's LAN. Refreshed several times a day.
CRE_PLACES_URL = "https://publicacionexterna.azurewebsites.net/publicaciones/places"
CRE_PRICES_URL = "https://publicacionexterna.azurewebsites.net/publicaciones/prices"


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Cheap flat-earth distance, good enough for a 30 km radius."""
    return math.hypot((lat1 - lat2) * 111, (lon1 - lon2) * 95)


async def _fetch_pemex_near(
    lat: float, lon: float, radius_km: float, max_stations: int,
) -> tuple[list[dict], str | None]:
    """Return (stations, error). Each station has name, distance_km,
    lat, lon, regular_mxn_l, premium_mxn_l, diesel_mxn_l."""
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(CRE_PLACES_URL, timeout=30) as r:
                if r.status >= 400:
                    return [], f"places HTTP {r.status}"
                places_xml = await r.text()
            async with http.get(CRE_PRICES_URL, timeout=30) as r:
                if r.status >= 400:
                    return [], f"prices HTTP {r.status}"
                prices_xml = await r.text()
    except Exception as exc:  # noqa: BLE001
        return [], f"{exc.__class__.__name__}: {exc}"

    try:
        places_root = ET.fromstring(places_xml)
        prices_root = ET.fromstring(prices_xml)
    except ET.ParseError as exc:
        return [], f"parse: {exc}"

    nearby: dict[str, dict[str, Any]] = {}
    for p in places_root:
        pid = p.get("place_id")
        if not pid:
            continue
        loc = p.find("location")
        if loc is None:
            continue
        try:
            x = float(loc.findtext("x") or 0)  # lon
            y = float(loc.findtext("y") or 0)  # lat
        except ValueError:
            continue
        d = _km(lat, lon, y, x)
        if d <= radius_km:
            nearby[pid] = {
                "place_id": pid,
                "name": p.findtext("name") or "?",
                "distance_km": round(d, 1),
                "lat": y, "lon": x,
                "regular_mxn_l": None,
                "premium_mxn_l": None,
                "diesel_mxn_l": None,
            }

    for p in prices_root:
        pid = p.get("place_id")
        if pid not in nearby:
            continue
        for gp in p.findall("gas_price"):
            try:
                v = float(gp.text or 0) or None
            except (ValueError, TypeError):
                v = None
            if gp.get("type") == "regular":
                nearby[pid]["regular_mxn_l"] = v
            elif gp.get("type") == "premium":
                nearby[pid]["premium_mxn_l"] = v
            elif gp.get("type") == "diesel":
                nearby[pid]["diesel_mxn_l"] = v

    stations = sorted(nearby.values(), key=lambda s: s["distance_km"])
    return stations[:max_stations], None


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
            "lat":                    {"type": "number"},
            "lon":                    {"type": "number"},
            "pemex_radius_km":        {"type": "number"},
            "pemex_max_stations":     {"type": "integer"},
            "costco_manual_usd_gal": {"type": ["number", "null"]},
            "costco_updated_at":     {"type": ["string", "null"]},
            "usd_per_mxn":            {"type": ["number", "null"]},
            "eia_api_key":            {"type": ["string", "null"],
                                        "description": "Free key from eia.gov/opendata — falls back to DEMO_KEY"},
            "try_costco_scrape":      {"type": "boolean"},
        },
    }
    default_config = {
        "lat": 31.025,
        "lon": -114.838,
        "pemex_radius_km": 30,
        "pemex_max_stations": 6,
        "costco_manual_usd_gal": None,
        "costco_updated_at": None,
        "usd_per_mxn": None,
        "eia_api_key": None,
        "try_costco_scrape": False,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        costco_manual = config.get("costco_manual_usd_gal")
        rate = config.get("usd_per_mxn")
        lat = float(config.get("lat", 31.025))
        lon = float(config.get("lon", -114.838))

        # Real: EIA California retail weekly average
        eia_key = (
            config.get("eia_api_key")
            or os.getenv("EIA_API_KEY")
            or "DEMO_KEY"
        )
        ca_avg_usd_gal, ca_avg_date = await _fetch_eia_california_regular(eia_key)

        # Real: Pemex live per-station prices from Mexican gov feed
        pemex_stations, pemex_err = await _fetch_pemex_near(
            lat, lon,
            float(config.get("pemex_radius_km", 30)),
            int(config.get("pemex_max_stations", 6)),
        )
        # Nearest station's regular price is our "Pemex SF" headline
        pemex_regular_mxn_l = None
        pemex_nearest = None
        for s in pemex_stations:
            if s.get("regular_mxn_l"):
                pemex_regular_mxn_l = s["regular_mxn_l"]
                pemex_nearest = s
                break

        pemex_usd_gal = None
        if pemex_regular_mxn_l and rate:
            # 1 US gallon = 3.78541 L
            pemex_usd_gal = round(pemex_regular_mxn_l * float(rate) * 3.78541, 2)

        # Best effort Costco scrape (usually fails — disabled by default)
        scraped, costco_source = (None, "manual")
        if config.get("try_costco_scrape"):
            scraped, costco_source = await _scrape_costco_calexico(
                float(costco_manual) if costco_manual is not None else None,
            )
        costco_val = scraped if scraped is not None else (
            float(costco_manual) if costco_manual is not None else None
        )

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
            "pemex_stations": pemex_stations,
            "pemex_nearest": pemex_nearest,
            "pemex_regular_mxn_l": pemex_regular_mxn_l,
            "pemex_usd_gal_equiv": pemex_usd_gal,
            "pemex_source": ("cre.gob.mx" if pemex_stations else "unavailable"),
            "pemex_error": pemex_err,
            "usd_per_mxn": rate,
            "savings_usd_gal_going_north": delta,
            "sources": {
                "ca_avg": "US EIA API v2 — California retail weekly regular",
                "pemex":  "CRE (Mexican gov) publicacionexterna feed — live per-station",
                "costco": "Manual (Costco/GasBuddy don't serve prices to scrapers)",
            },
        }
