"""RSS / Atom feed reader widget.

Plain stdlib XML parser — no feedparser dep. Configure as many feed
URLs as you like; the widget pulls the latest N items from each.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from typing import Any

import aiohttp

from .base import Widget


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return unescape(s).strip()


def _parse_feed(xml_text: str, source_url: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    # RSS: <rss><channel><item>...</item></channel></rss>
    # Atom: <feed><entry>...</entry></feed>
    items = []
    title = ""
    channel = root.find("channel")
    if channel is not None:
        title = _strip(channel.findtext("title") or "")
        for it in channel.findall("item"):
            items.append({
                "title": _strip(it.findtext("title") or ""),
                "link": (it.findtext("link") or "").strip(),
                "published": (it.findtext("pubDate") or "").strip(),
                "summary": _strip(it.findtext("description") or "")[:300],
            })
    else:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        title = _strip(root.findtext("a:title", default="", namespaces=ns))
        for it in root.findall("a:entry", ns):
            link_el = it.find("a:link", ns)
            link = link_el.get("href") if link_el is not None else ""
            items.append({
                "title": _strip(it.findtext("a:title", default="", namespaces=ns)),
                "link": link.strip(),
                "published": (it.findtext("a:updated", default="", namespaces=ns) or "").strip(),
                "summary": _strip(it.findtext("a:summary", default="", namespaces=ns))[:300],
            })
    return {"source": source_url, "title": title, "items": items}


class NewsWidget(Widget):
    id = "news"
    kind = "news"
    name = "News"
    description = (
        "Latest items from any RSS / Atom feeds you configure. Defaults "
        "to NHC tropical outlook + USGS quake feed text. Add Baja news "
        "outlets via Settings."
    )
    refresh_seconds = 30 * 60
    default_tab = "Community"
    default_position = 70

    config_schema = {
        "type": "object",
        "properties": {
            "feeds": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["url"],
                    "properties": {
                        "label": {"type": "string"},
                        "url":   {"type": "string", "format": "uri"},
                    },
                },
            },
            "max_items_per_feed": {"type": "integer", "minimum": 1, "maximum": 20},
        },
    }
    default_config = {
        "feeds": [
            {"label": "NHC Eastern Pacific",
             "url": "https://www.nhc.noaa.gov/index-ep.xml"},
            {"label": "USGS quakes (24h)",
             "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_day.atom"},
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
                        headers={"User-Agent": "SolarSage/1.0 (news widget)"},
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
