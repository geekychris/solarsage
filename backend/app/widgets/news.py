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


def _regex_fallback(xml_text: str, source_url: str) -> dict[str, Any]:
    """When strict XML parsing chokes (bad entities, unescaped ampersands,
    HTML in RSS content), grab item titles + links with regex. Not
    RSS-compliant but survives most malformed real-world feeds.
    """
    items = []
    # Try RSS item blocks
    for block in re.findall(r"(?is)<item\b[^>]*>(.*?)</item>", xml_text):
        title_m = re.search(r"(?is)<title\b[^>]*>(.*?)</title>", block)
        link_m = re.search(r"(?is)<link\b[^>]*>(.*?)</link>", block) \
                 or re.search(r'(?is)<link\b[^>]*href="([^"]+)"', block)
        pub_m = re.search(r"(?is)<pubDate\b[^>]*>(.*?)</pubDate>", block)
        desc_m = re.search(r"(?is)<description\b[^>]*>(.*?)</description>", block)
        if not title_m:
            continue
        items.append({
            "title": _strip(_uncdata(title_m.group(1))),
            "link": _strip(_uncdata(link_m.group(1))) if link_m else "",
            "published": _strip(pub_m.group(1)) if pub_m else "",
            "summary": _strip(_uncdata(desc_m.group(1)))[:300] if desc_m else "",
        })
    # Try Atom entries as fallback
    if not items:
        for block in re.findall(r"(?is)<entry\b[^>]*>(.*?)</entry>", xml_text):
            title_m = re.search(r"(?is)<title\b[^>]*>(.*?)</title>", block)
            link_m = re.search(r'(?is)<link\b[^>]*href="([^"]+)"', block)
            pub_m = re.search(r"(?is)<updated\b[^>]*>(.*?)</updated>", block)
            if not title_m:
                continue
            items.append({
                "title": _strip(_uncdata(title_m.group(1))),
                "link": link_m.group(1).strip() if link_m else "",
                "published": _strip(pub_m.group(1)) if pub_m else "",
                "summary": "",
            })
    title_m = re.search(r"(?is)<channel\b[^>]*>.*?<title\b[^>]*>(.*?)</title>", xml_text)
    title = _strip(_uncdata(title_m.group(1))) if title_m else ""
    return {"source": source_url, "title": title, "items": items,
            "parser": "regex_fallback"}


def _uncdata(s: str) -> str:
    m = re.match(r"(?is)\s*<!\[CDATA\[(.*)\]\]>\s*$", s or "")
    return m.group(1) if m else (s or "")


def _parse_feed(xml_text: str, source_url: str) -> dict[str, Any]:
    """Try strict XML first; on any parse error fall back to regex."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return _regex_fallback(xml_text, source_url)

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
