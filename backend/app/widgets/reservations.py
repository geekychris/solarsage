"""Reservations widget — paste in iCal URLs (Airbnb / Vrbo / Calendly).

Parses VEVENT blocks with a tiny stdlib parser (no `icalendar` dep).
Shows the next N upcoming bookings.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

import aiohttp

from .base import Widget


def _unfold(text: str) -> str:
    # iCalendar lines can be wrapped; subsequent lines start with a space.
    return re.sub(r"\r?\n[ \t]", "", text)


def _parse_ical(text: str) -> list[dict[str, Any]]:
    text = _unfold(text)
    events: list[dict[str, Any]] = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.DOTALL):
        e: dict[str, Any] = {}
        for ln in block.splitlines():
            if ":" not in ln:
                continue
            k, v = ln.split(":", 1)
            key = k.split(";", 1)[0].strip().upper()
            val = v.strip()
            if key == "SUMMARY":     e["summary"] = val
            elif key == "DTSTART":   e["start"]   = val
            elif key == "DTEND":     e["end"]     = val
            elif key == "UID":       e["uid"]     = val
            elif key == "DESCRIPTION": e["description"] = val[:200]
            elif key == "STATUS":    e["status"]  = val
        if "start" in e:
            events.append(e)
    return events


def _ical_date(s: str) -> str | None:
    # 20260701T220000Z, 20260701, 20260701T160000 (local)
    s = s.strip()
    if not s:
        return None
    if "T" in s:
        d = s[:8]
    else:
        d = s
    if len(d) != 8 or not d.isdigit():
        return None
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


class ReservationsWidget(Widget):
    id = "reservations"
    kind = "reservations"
    name = "Reservations"
    description = (
        "Upcoming bookings from any iCal URLs you paste in — Airbnb host "
        "calendars, Vrbo, etc. Useful for syncing pre-cool / vacant-mode "
        "logic with check-in / check-out dates."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Community"
    default_position = 75

    config_schema = {
        "type": "object",
        "properties": {
            "calendars": {
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
            "show_days_back": {"type": "integer", "minimum": 0, "maximum": 30},
            "max_upcoming": {"type": "integer", "minimum": 1, "maximum": 50},
        },
    }
    default_config = {
        "calendars": [],
        "show_days_back": 0,
        "max_upcoming": 10,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        cals = config.get("calendars") or []
        days_back = int(config.get("show_days_back", 0))
        max_n = int(config.get("max_upcoming", 10))
        cutoff = (date.today().toordinal() - days_back)

        events: list[dict[str, Any]] = []
        async with aiohttp.ClientSession() as http:
            for cal in cals:
                url = cal.get("url")
                if not url:
                    continue
                try:
                    async with http.get(
                        url, timeout=30,
                        headers={"User-Agent": "SolarSage/1.0 (reservations)"},
                    ) as r:
                        r.raise_for_status()
                        text = await r.text()
                except Exception as exc:  # noqa: BLE001
                    events.append({
                        "source": cal.get("label") or url,
                        "error": str(exc),
                    })
                    continue
                for ev in _parse_ical(text):
                    start = _ical_date(ev.get("start", ""))
                    end = _ical_date(ev.get("end", ""))
                    if not start:
                        continue
                    try:
                        if date.fromisoformat(start).toordinal() < cutoff:
                            continue
                    except ValueError:
                        continue
                    events.append({
                        "source": cal.get("label") or url,
                        "summary": ev.get("summary"),
                        "start": start,
                        "end": end,
                        "status": ev.get("status"),
                        "uid": ev.get("uid"),
                    })

        events.sort(key=lambda e: e.get("start") or "")
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "upcoming": [e for e in events if "error" not in e][:max_n],
            "errors": [e for e in events if "error" in e],
        }
