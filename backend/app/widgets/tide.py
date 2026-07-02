"""Tide table widget — supports WorldTides API + tidetime.org scraper.

Tide predictions don't change intra-day, so the widget refreshes once
per day and skips fetch on backend restart if the cached data is
still <20 h old. That's the fix for "WorldTides free-tier burned in
one day" — every deploy used to trigger a fresh fetch.

Config:
    {"provider": "tidetime" | "worldtides",
     "stations": [
       {"id": "san_felipe",  "name": "San Felipe",
        "lat": 31.025, "lon": -114.838,
        "tidetime_slug": "north-america/mexico/san-felipe"},
       {"id": "puertecitos", "name": "Puertecitos",
        "lat": 30.351, "lon": -114.642,
        "tidetime_slug": "north-america/mexico/puertecitos"}],
     "days": 7}

Data shape (either provider):
    {"fetched_at": <iso8601>, "provider": "...",
     "stations": [{"id", "name", "extremes": [
        {"dt": <unix>, "iso": "...+00:00", "height_m": 1.42, "type": "High"}
     ]}]}
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

WORLDTIDES_URL   = "https://www.worldtides.info/api/v3"
TIDETIME_BASE    = "https://www.tidetime.org"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

# tidetime.org embeds the tide extremes as a chain of JSON objects of
# the form ``{"date": <unix_seconds>, "height": "<meters>"}``.
_TIDETIME_EXTREMES_RE = re.compile(
    r'\{"date":\s*(\d+),\s*"height":\s*"?(-?\d+(?:\.\d+)?)"?\}'
)


def _classify_extremes(pairs: list[tuple[int, float]]) -> list[dict[str, Any]]:
    """Given a chronologically-ordered list of (unix_seconds, height_m)
    extremes, tag each as High or Low. An entry is High when its height
    is greater than both neighbours; Low otherwise. First / last extreme
    is tagged relative to its single neighbour."""
    out: list[dict[str, Any]] = []
    for i, (dt, h) in enumerate(pairs):
        left  = pairs[i - 1][1] if i > 0            else None
        right = pairs[i + 1][1] if i + 1 < len(pairs) else None
        if right is not None:
            is_high = h > right
        elif left is not None:
            is_high = h > left
        else:
            is_high = h > 0
        out.append({
            "dt": dt,
            "iso": datetime.fromtimestamp(dt, tz=timezone.utc).isoformat(),
            "height_m": round(h, 3),
            "type": "High" if is_high else "Low",
        })
    return out


async def _fetch_tidetime_station(
    http: aiohttp.ClientSession, slug: str, days: int,
) -> list[dict[str, Any]]:
    """Scrape tidetime.org's page for one station. Returns extremes for
    the next ``days`` days."""
    url = f"{TIDETIME_BASE}/{slug}.htm"
    async with http.get(
        url, headers={"User-Agent": UA}, timeout=20,
    ) as r:
        r.raise_for_status()
        html = await r.text()
    hits = _TIDETIME_EXTREMES_RE.findall(html)
    if not hits:
        raise RuntimeError(f"no extremes parsed from {url}")
    pairs = [(int(dt), float(h)) for dt, h in hits]
    # De-dupe and sort
    pairs = sorted(set(pairs), key=lambda x: x[0])
    horizon = int(datetime.now(timezone.utc).timestamp()) + days * 86_400
    pairs = [p for p in pairs if p[0] <= horizon]
    return _classify_extremes(pairs)


async def _fetch_worldtides_station(
    http: aiohttp.ClientSession, api_key: str,
    lat: float, lon: float, days: int,
) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    params = {
        "extremes": "", "lat": lat, "lon": lon,
        "key": api_key, "date": today, "days": days,
    }
    async with http.get(WORLDTIDES_URL, params=params, timeout=30) as r:
        payload = await r.json(content_type=None)
    if payload.get("status") not in (200, None):
        raise RuntimeError(
            f"WorldTides {payload.get('status')}: "
            f"{payload.get('error') or payload}"
        )
    extremes = []
    for e in payload.get("extremes") or []:
        extremes.append({
            "dt": int(e["dt"]),
            "iso": e.get("date"),
            "height_m": round(float(e["height"]), 3),
            "type": e.get("type"),
        })
    return extremes


class TideWidget(Widget):
    id = "tides"
    kind = "tides"
    name = "Tide tables"
    description = (
        "High/low tide predictions for configured stations. Default "
        "provider is tidetime.org (scrape, no rate limit, no API key). "
        "WorldTides is available as an opt-in for users with a paid "
        "key. Tide tables don't change intra-day, so the widget "
        "refreshes once/day and skips fetches on restart if cached "
        "data is still <20 h old."
    )
    # Once per day is plenty — extremes are deterministic.
    refresh_seconds = 24 * 3600
    # Skip re-fetch on backend restart if cached state is still fresh.
    max_stale_seconds = 20 * 3600
    default_tab = "Outdoor"
    default_position = 10

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at": {"type": "string", "format": "date-time"},
            "provider":   {"type": "string"},
            "stations": {"type": "array"},
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "provider": {"enum": ["tidetime", "worldtides"]},
            "days":     {"type": "integer", "minimum": 1, "maximum": 14},
            "stations": {"type": "array"},
        },
    }

    default_config = {
        "provider": "tidetime",
        "days": 7,
        "stations": [
            {"id": "san_felipe", "name": "San Felipe",
             "lat": 31.025, "lon": -114.838,
             "tidetime_slug": "north-america/mexico/san-felipe"},
            {"id": "puertecitos", "name": "Puertecitos",
             "lat": 30.351, "lon": -114.642,
             "tidetime_slug": "north-america/mexico/puertecitos"},
        ],
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        provider = str(config.get("provider") or "tidetime").lower()
        days = int(config.get("days", 7))
        stations = list(config.get("stations") or [])
        # Backfill tidetime_slug from defaults for stations whose
        # persisted config predates the provider switch.
        default_slugs = {
            s["id"]: s.get("tidetime_slug")
            for s in self.default_config.get("stations") or []
            if s.get("tidetime_slug")
        }
        for st in stations:
            if provider == "tidetime" and not st.get("tidetime_slug"):
                fallback = default_slugs.get(st.get("id"))
                if fallback:
                    st["tidetime_slug"] = fallback

        results: list[dict[str, Any]] = []
        async with aiohttp.ClientSession() as http:
            for st in stations:
                if provider == "worldtides":
                    api_key = os.getenv("WORLDTIDES_API_KEY")
                    if not api_key:
                        raise RuntimeError(
                            "WORLDTIDES_API_KEY not set — either add a key "
                            "or switch provider to 'tidetime'."
                        )
                    extremes = await _fetch_worldtides_station(
                        http, api_key, st["lat"], st["lon"], days,
                    )
                else:
                    slug = st.get("tidetime_slug") or ""
                    if not slug:
                        raise RuntimeError(
                            f"station {st.get('id')} has no tidetime_slug; "
                            f"set one or switch provider to 'worldtides'"
                        )
                    extremes = await _fetch_tidetime_station(http, slug, days)
                results.append({
                    "id": st.get("id"),
                    "name": st.get("name"),
                    "lat": st.get("lat"),
                    "lon": st.get("lon"),
                    "extremes": extremes,
                })

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "stations": results,
        }
