"""Parse the HOA weekly-activities PDF into discrete events.

The PDF is generated from Excel and has a roughly tabular layout:

    Weekly Activities Schedule: June 29 – 5 July 2026

    Monday June 29th             |  Tuesday 30th
    7:30 Lap Swimming            |  7:30 Lap Swimming
    8:30 Water Aerobics          |  6:30 Movie Night
    5:00 FULL MOON MIXER         |  7:00 Evening Pickleball

pypdf's text extraction collapses the columns to a single stream, so we
parse by walking forward, splitting on day-header lines and pulling
``H:MM <title>`` entries out of each block.

AM/PM is implicit. Heuristic: times after ``12:00`` in reading order are
PM; ``12:00`` is noon. Times ≤ 11:30 that occur AFTER a PM-anchor in the
same day's block are treated as PM too (this catches a stray morning
listing rearranged below the noon entry).

We tag events as ``special`` when they aren't part of the routine
catalog (lap swim, pickleball, etc.). The reminder scheduler defaults to
firing for ``special`` events only.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

import aiohttp
import pypdf

log = logging.getLogger("eg4.events.parser")

DAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# A day header looks like "Monday June 29th", "Tuesday 30th",
# "Saturday 4th of July INDEPENDENCE DAY", "Sunday 5th"
DAY_HEADER_RE = re.compile(
    r"^\s*(?P<dow>monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"\b(?P<rest>[^\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)

# Event line: "H:MM <title>" — title runs to end of line.
EVENT_LINE_RE = re.compile(
    r"^\s*(?P<h>\d{1,2}):(?P<m>\d{2})\s+(?P<title>.+?)\s*$",
    re.MULTILINE,
)

# Routine recurring activities — these aren't surfaced as "today's
# events" because every day has them. The reminder scheduler also skips
# these by default (is_special=False).
ROUTINE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\blap\s+swim", r"\bpickleball", r"\bwork[\s-]*in\s+tennis",
        r"\bwater\s+aerobics", r"\bwater\s+volleyball",
        r"\bmexican\s+train", r"\bsign-?up", r"\bopen\s+play",
        r"\blearn to play",
    )
]

# Words that strongly indicate a PM time even if H < 12
PM_KEYWORDS_RE = re.compile(
    r"\b(?:movie|mixer|night|tournament|poker|bingo|karaoke|dinner|"
    r"evening|scramble|happy hour|theater|theatre)\b",
    re.IGNORECASE,
)


@dataclass
class ExtractedEvent:
    """One row from the parsed PDF, not yet persisted."""
    source_ref: str
    title: str
    starts_at: datetime
    raw_time: str
    is_special: bool
    notes: str | None = None


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _resolve_date(
    line: str, dow_name: str, week_anchor: date,
) -> date | None:
    """Resolve a day-header line into a concrete date.

    Strategy:
    1. If the header contains an explicit "MonthName D" or "D{th,st,nd,rd}",
       compute the actual date from the anchor's month.
    2. Otherwise advance from the week's anchor (Monday) by the offset
       implied by the day-of-week.
    """
    # Day-of-week → offset relative to Monday
    target_dow = DAY_NAMES[dow_name.lower()]
    candidate = week_anchor + timedelta(days=target_dow)

    # Look for an explicit day number in the rest of the header
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", line)
    if m:
        day_num = int(m.group(1))
        # Try the anchor's month first; if it doesn't match the day-of-week,
        # try the next month (week crosses a month boundary).
        for delta in (0, 1):
            month_anchor = (
                date(candidate.year, candidate.month, 1)
                if delta == 0
                else (
                    date(candidate.year + (candidate.month == 12),
                         (candidate.month % 12) + 1, 1)
                )
            )
            try:
                d = date(month_anchor.year, month_anchor.month, day_num)
            except ValueError:
                continue
            if d.weekday() == target_dow and abs((d - candidate).days) <= 4:
                return d
    return candidate


def _to_24h(
    h: int, m: int, title: str, day_block: str,
    *, leading_zero: bool = False,
) -> tuple[int, int]:
    """Best-effort AM/PM resolution. Returns (h, m) in 24h."""
    if h == 12:
        # 12:00 → noon
        return 12, m
    if h >= 13:
        return h, m
    # "08:00" with a leading zero is almost always written by someone
    # who means AM — Excel typically writes 8 PM as just "8:00 PM" or
    # "8:00". Strong AM signal that overrides keyword heuristics.
    if leading_zero:
        return h, m
    title_low = title.lower()
    # Strong PM signals on title
    if PM_KEYWORDS_RE.search(title_low):
        return h + 12, m
    # Look at the day's block: if a "12:00" or "1:00" entry appears
    # before this one (in text order), we're already past noon.
    before, _sep, _after = day_block.partition(f"{h}:{m:02d}")
    if re.search(r"\b12:\d{2}\b", before):
        # past noon
        return h + 12, m
    if re.search(r"\b1[3-9]:\d{2}\b", before):
        return h + 12, m
    # Default: morning
    return h, m


def _classify(title: str) -> bool:
    """True if event is "special" (not routine)."""
    low = title.lower()
    return not any(p.search(low) for p in ROUTINE_PATTERNS)


def _split_day_blocks(text: str) -> list[tuple[str, str, str]]:
    """Split the PDF text into (day_name, header_line, block_text) tuples,
    in reading order."""
    matches = list(DAY_HEADER_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        header = m.group(0).strip()
        # Normalize dow to lowercase so downstream code (and tests)
        # don't have to worry about capitalization variants.
        out.append((m.group("dow").lower(), header, block))
    return out


def _week_anchor_from_title(text: str, fallback: date) -> date:
    """Find the "June 29 – 5 July 2026" header and pull the start Monday."""
    title_re = re.compile(
        r"(?i)(?:weekly\s+activities\s+schedule|week(?:ly)?\s+of)\s*:\s*"
        r"(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2})"
        r"(?:\s*[-–]\s*(?:(?P<d2>\d{1,2})\s*(?P<m2>[A-Za-z]+)?|"
        r"(?P<m2b>[A-Za-z]+)\s+(?P<d2b>\d{1,2})))?"
        r".*?(?P<y>20\d{2})"
    )
    m = title_re.search(text)
    if not m:
        return fallback
    months = (
        "january february march april may june july august september "
        "october november december"
    ).split()
    try:
        mo = months.index(m.group("m1").lower()) + 1
        d = int(m.group("d1"))
        y = int(m.group("y"))
        return date(y, mo, d)
    except (ValueError, AttributeError):
        return fallback


async def fetch_and_parse(
    url: str, *, fallback_today: date | None = None,
) -> list[ExtractedEvent]:
    """Download the weekly PDF and extract events. Network errors raise."""
    fallback_today = fallback_today or date.today()

    async with aiohttp.ClientSession() as http:
        async with http.get(
            url,
            timeout=30,
            headers={"User-Agent": "SolarSage/1.0 (events parser)"},
        ) as r:
            r.raise_for_status()
            blob = await r.read()

    reader = pypdf.PdfReader(io.BytesIO(blob))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # The fallback for the week's Monday: this Monday relative to fallback_today
    monday_fallback = fallback_today - timedelta(days=fallback_today.weekday())
    week_monday = _week_anchor_from_title(text, monday_fallback)

    events: list[ExtractedEvent] = []
    for dow, header, block in _split_day_blocks(text):
        d = _resolve_date(header, dow, week_monday)
        if d is None:
            continue
        for em in EVENT_LINE_RE.finditer(block):
            title = em.group("title").strip()
            # Discard noise lines that are just sub-info ("11:30 sign-up
            # time/game 11:45" — these get folded into the prior entry).
            if title.lower().startswith(("sign-up", "sign up")):
                continue
            raw_h = em.group("h")
            h, m = _to_24h(
                int(raw_h), int(em.group("m")), title, block,
                leading_zero=raw_h.startswith("0") and len(raw_h) == 2,
            )
            try:
                starts_at = datetime.combine(d, time(h, m))
            except ValueError:
                continue
            raw = f"{em.group('h')}:{em.group('m')}"
            short = re.sub(r"\s+", " ", title)[:80]
            source_ref = (
                "hoa:weekly:"
                f"{d.isoformat()}:{h:02d}{m:02d}:"
                f"{hashlib.md5(short.lower().encode()).hexdigest()[:8]}"
            )
            events.append(
                ExtractedEvent(
                    source_ref=source_ref,
                    title=short,
                    starts_at=starts_at,
                    raw_time=raw,
                    is_special=_classify(title),
                )
            )

    # Dedup on source_ref (handles the occasional duplicate from layout
    # weirdness)
    seen: dict[str, ExtractedEvent] = {}
    for e in events:
        seen.setdefault(e.source_ref, e)
    return list(seen.values())


def iter_today(
    events: Iterable[ExtractedEvent], today: date,
) -> list[ExtractedEvent]:
    return [e for e in events if e.starts_at.date() == today]
