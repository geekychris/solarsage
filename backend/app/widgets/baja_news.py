"""Baja California news — curated RSS feeds.

Same parser as ``news.py``; ships with a Baja-focused default feed list
so users don't have to hunt for RSS URLs. Users can add/remove via
Settings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget
from .news import _parse_feed


class BajaNewsWidget(Widget):
    id = "baja_news"
    kind = "news"          # reuses the news renderer
    name = "Baja news"
    description = (
        "Local Baja California headlines. Defaults to major regional "
        "outlets — swap them via Settings for whichever feeds you follow."
    )
    refresh_seconds = 30 * 60
    default_tab = "Community"
    default_position = 68

    config_schema = {
        "type": "object",
        "properties": {
            "feeds": {"type": "array"},
            "max_items_per_feed": {"type": "integer"},
        },
    }
    default_config = {
        "feeds": [
            {"label": "El Imparcial (Tijuana/Mexicali)",
             "url": "https://www.elimparcial.com/rss/mexicali.xml"},
            {"label": "BCS Noticias",
             "url": "https://www.bcsnoticias.mx/feed/"},
            {"label": "Tribuna de San Luis",
             "url": "https://www.tribuna.com.mx/rss/tribuna-de-san-luis"},
        ],
        "max_items_per_feed": 5,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        feeds = config.get("feeds") or []
        max_n = int(config.get("max_items_per_feed", 5))
        results = []
        async with aiohttp.ClientSession() as http:
            for feed in feeds:
                url = feed.get("url")
                if not url:
                    continue
                try:
                    async with http.get(
                        url, timeout=20,
                        headers={"User-Agent": "SolarSage/1.0 (baja news)"},
                    ) as r:
                        r.raise_for_status()
                        body = await r.text()
                    parsed = _parse_feed(body, url)
                    parsed["label"] = feed.get("label") or parsed.get("title") or url
                    parsed["items"] = parsed["items"][:max_n]
                    results.append(parsed)
                except Exception as exc:  # noqa: BLE001
                    results.append({
                        "source": url,
                        "label": feed.get("label") or url,
                        "error": str(exc),
                        "items": [],
                    })
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "feeds": results,
        }
