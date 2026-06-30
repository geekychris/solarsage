"""El Dorado Ranch HOA recreational activities widget.

The page is public but unstructured — most content is text blocks plus
linked PDFs (monthly + weekly calendars). We extract whatever obvious
event-shaped content we can and always include the PDF links so the user
has a one-click path to the full schedule.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .base import Widget

DEFAULT_URL = (
    "https://www.eldoradoranchhoa.com.mx/page/29035~797884/"
    "ranch-recreational-activities"
)


def _strip_tags(html: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", "", html)
    text = re.sub(r"(?is)<style.*?</style>", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_pdf_links(html: str, base_url: str) -> list[dict[str, str]]:
    """Pull <a href="...pdf"> links + their visible text."""
    out: list[dict[str, str]] = []
    pattern = re.compile(
        r'<a\b[^>]*?href=["\']([^"\']+?\.pdf[^"\']*)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for href, inner in pattern.findall(html):
        label = _strip_tags(inner) or href.rsplit("/", 1)[-1]
        out.append({"url": urljoin(base_url, href), "label": label})
    # De-dup by URL but preserve order
    seen: set[str] = set()
    deduped = []
    for link in out:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        deduped.append(link)
    return deduped


MONTH_NAMES = (
    "january february march april may june july august september october "
    "november december"
).split()
MONTH_RE = re.compile(
    r"\b(?:" + "|".join(MONTH_NAMES) + r")\b[^a-z]*\b20\d{2}\b",
    re.IGNORECASE,
)


YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _label_year(label: str) -> int | None:
    m = YEAR_RE.search(label)
    return int(m.group(1)) if m else None


def _classify_calendar_links(
    links: list[dict[str, str]], today: date | None = None,
) -> dict[str, Any]:
    """Best-effort: find 'monthly' and 'weekly' calendar PDFs by label.

    The HOA labels weekly calendars as "June 29 - July 5, 2026" and monthly
    ones as bare "June 2026" — neither contains the words "weekly"/"monthly".
    The page also lists historical calendars going back years, so we must
    prefer current-year labels over older ones.
    """
    today = today or datetime.now(timezone.utc).date()
    year = today.year

    monthly_candidates: list[dict[str, str]] = []
    weekly_candidates: list[dict[str, str]] = []
    for link in links:
        lab = link["label"].strip()
        low = lab.lower()
        looks_weekly = (
            "week" in low
            or re.search(r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b", lab)
            or re.search(r"-\s*[A-Za-z]+\s+\d{1,2}", lab)
        )
        looks_monthly = bool(MONTH_RE.fullmatch(lab) or MONTH_RE.match(lab))
        if looks_weekly:
            weekly_candidates.append(link)
            continue
        if looks_monthly:
            monthly_candidates.append(link)

    def _pick(candidates: list[dict[str, str]]) -> dict[str, str] | None:
        if not candidates:
            return None
        # Current year wins; otherwise undated; otherwise the most recent year.
        current = [c for c in candidates if _label_year(c["label"]) == year]
        if current:
            return current[0]
        undated = [c for c in candidates if _label_year(c["label"]) is None]
        if undated:
            return undated[0]
        return max(candidates, key=lambda c: _label_year(c["label"]) or 0)

    return {
        "monthly_pdf": _pick(monthly_candidates),
        "weekly_pdf": _pick(weekly_candidates),
    }


def _extract_announcements(html: str) -> list[str]:
    """Pick up short text announcements ("See you in October 2026!" etc.).

    Heuristic: take all paragraphs whose stripped text is between 8 and 200
    characters and contains a year, month, or "today/this week" keyword.
    """
    paragraphs = re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", html)
    months = (
        "january february march april may june july august september october "
        "november december"
    ).split()
    out = []
    for para in paragraphs:
        text = _strip_tags(para)
        if not (8 <= len(text) <= 200):
            continue
        low = text.lower()
        if any(m in low for m in months) or "today" in low or "this week" in low \
                or re.search(r"\b20\d{2}\b", low):
            out.append(text)
    # de-dup while preserving order
    seen: set[str] = set()
    deduped = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)
    return deduped[:10]


class HoaWidget(Widget):
    id = "hoa"
    kind = "hoa"
    name = "El Dorado Ranch — activities"
    description = (
        "Recreational activities at El Dorado Ranch (San Felipe). The HOA "
        "page doesn't publish a structured calendar, so the widget surfaces "
        "the monthly + weekly calendar PDFs plus any inline announcements "
        "it can detect. Click the PDF for the full schedule."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Community"
    default_position = 50

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at": {"type": "string", "format": "date-time"},
            "url": {"type": "string"},
            "monthly_pdf": {"type": ["object", "null"]},
            "weekly_pdf": {"type": ["object", "null"]},
            "all_pdfs": {"type": "array"},
            "announcements": {"type": "array", "items": {"type": "string"}},
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "format": "uri"},
        },
    }

    default_config = {"url": DEFAULT_URL}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        url = config.get("url") or DEFAULT_URL
        async with aiohttp.ClientSession() as http:
            async with http.get(
                url,
                timeout=30,
                headers={"User-Agent": "SolarSage/1.0 (HOA widget)"},
            ) as r:
                r.raise_for_status()
                html = await r.text()

        pdfs = _extract_pdf_links(html, url)
        classified = _classify_calendar_links(pdfs)
        announcements = _extract_announcements(html)

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "monthly_pdf": classified["monthly_pdf"],
            "weekly_pdf": classified["weekly_pdf"],
            "all_pdfs": pdfs,
            "announcements": announcements,
        }
