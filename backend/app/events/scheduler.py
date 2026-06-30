"""Reminder scheduler.

Two responsibilities, run on the same one-minute tick:

1. **Ingest** — once an hour, pull the HOA weekly PDF (taking the URL
   from the HOA widget's cached data so we don't re-scrape the page)
   and upsert ``hoa`` events. Default reminders are seeded on first
   insert; subsequent ingests leave them alone.

2. **Fire** — for every event whose ``starts_at`` is in the future,
   walk its reminders. If a reminder's fire time has passed in the
   last 65 seconds and it hasn't been fired yet, POST it to the TTS
   service.

The scheduler reads the configured timezone from the settings KV
table (``tz``) — defaults to ``America/Tijuana``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time as _time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import parser as event_parser
from .store import Event, EventStore, Reminder
from .tts import say

log = logging.getLogger("eg4.events.scheduler")

INGEST_INTERVAL_SECONDS = 60 * 60          # hourly
TICK_SECONDS = 60                          # check reminders every minute


def _default_reminders(ev_start_local: datetime) -> list[Reminder]:
    """Out-of-the-box reminder set for a freshly ingested special event.

    Two reminders:
    * 60 minutes before
    * "morning of" — 09:00 local — but only if the event is later than
      11:00 local that day (otherwise the morning-of and 60-min
      reminders collapse into the same thing).
    """
    out: list[Reminder] = [
        Reminder(id="", event_id="", minutes_before=60, mode="tts"),
    ]
    if ev_start_local.hour >= 11:
        morning = ev_start_local.replace(hour=9, minute=0, second=0, microsecond=0)
        minutes_before = max(
            1, int((ev_start_local - morning).total_seconds() // 60)
        )
        out.append(
            Reminder(id="", event_id="", minutes_before=minutes_before,
                     mode="tts")
        )
    return out


def _local_tz(settings_tz: str | None) -> timezone:
    """Resolve the configured tz to a fixed offset (zoneinfo would be
    nicer, but we don't want to add the dependency just for this)."""
    # Pi runs America/Tijuana → UTC-8 (PST) or UTC-7 (PDT). Use the
    # system localtime offset so we don't have to ship a zoneinfo bundle.
    return datetime.now().astimezone().tzinfo or timezone.utc


async def _ingest_once(
    store: EventStore,
    widget_store: "WidgetStore",  # noqa: F821 — main wires this in
) -> None:
    """Pull the HOA weekly PDF URL from the cached widget state, parse
    it, and upsert events."""
    state = await widget_store.get_state("hoa")
    if not state or not state.data:
        log.info("hoa widget has no data yet; skipping ingest")
        return
    weekly = (state.data or {}).get("weekly_pdf") or {}
    url = weekly.get("url")
    if not url:
        log.info("no weekly_pdf URL in hoa data; skipping ingest")
        return

    tz = _local_tz(None)
    today_local = datetime.now(tz).date()
    try:
        extracted = await event_parser.fetch_and_parse(
            url, fallback_today=today_local,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("HOA event parse failed: %s", exc)
        return

    log.info("HOA ingest: %d events parsed from %s", len(extracted), url)
    for x in extracted:
        # Render starts_at in local tz, then store as ISO with offset
        local_dt = x.starts_at.replace(tzinfo=tz)
        starts_iso = local_dt.isoformat()
        reminders = _default_reminders(local_dt) if x.is_special else []
        ev = Event(
            id="", source="hoa", source_ref=x.source_ref, title=x.title,
            starts_at=starts_iso, is_special=x.is_special,
            reminders=reminders,
        )
        await store.upsert_hoa(ev)

    # Drop events older than 24h so the table stays bounded
    cutoff = (datetime.now(tz) - timedelta(hours=24)).isoformat()
    pruned = await store.prune_past(cutoff)
    if pruned:
        log.info("pruned %d past events", pruned)


def _parse_iso_aware(s: str) -> datetime:
    """Parse our stored ISO timestamps; default UTC if no tz."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _fire_due_reminders(store: EventStore) -> None:
    now = datetime.now(timezone.utc).astimezone()
    window_floor = now - timedelta(seconds=TICK_SECONDS + 5)
    events = await store.list_events(starts_after=now.isoformat())
    for ev in events:
        if ev.snoozed:
            continue
        starts_at = _parse_iso_aware(ev.starts_at)
        for r in ev.reminders:
            if r.fired_at is not None:
                continue
            fire_time = starts_at - timedelta(minutes=r.minutes_before)
            if not (window_floor <= fire_time <= now):
                continue
            text = r.custom_text or _format_reminder_text(
                ev.title, starts_at, r.minutes_before,
            )
            log.info(
                "reminder firing: event=%s mins_before=%s text=%r",
                ev.id, r.minutes_before, text,
            )
            ok = await say(text)
            # Mark fired even on TTS failure — better to skip than
            # spam the user every minute trying to re-fire.
            await store.mark_fired(r.id, _time.time())
            if not ok:
                log.warning("reminder %s: TTS failed; marked fired anyway", r.id)


def _format_reminder_text(title: str, starts_at: datetime, minutes_before: int) -> str:
    hour = starts_at.strftime("%-I").lstrip("0") or "12"
    minute = starts_at.minute
    am_pm = starts_at.strftime("%p").lower()
    time_str = f"{hour}{':' + f'{minute:02d}' if minute else ''} {am_pm}"
    if minutes_before <= 75:
        return f"Reminder: {title} starts at {time_str}, in about {minutes_before} minutes."
    hours = round(minutes_before / 60, 1)
    if hours == int(hours):
        hours_str = f"{int(hours)} hours"
    else:
        hours_str = f"{hours} hours"
    return f"Heads up: {title} is today at {time_str}, in about {hours_str}."


async def run_reminder_scheduler(
    store: EventStore, widget_store: Any,
) -> None:
    """Top-level scheduler task: ingest + fire on the same loop."""
    last_ingest = 0.0
    # Stagger startup so we don't compete with the widget refreshers
    await asyncio.sleep(5)
    while True:
        try:
            now = _time.time()
            if now - last_ingest >= INGEST_INTERVAL_SECONDS:
                await _ingest_once(store, widget_store)
                last_ingest = now
            await _fire_due_reminders(store)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001
            log.exception("reminder scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)
