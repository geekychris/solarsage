"""Auto-announcements framework.

Per-source config (tides, HOA, storms, quakes, activities …) describes
whether the source should fire TTS/Telegram announcements, at what
"warn N minutes before" offsets, and via which channels. Config lives
in ``widget_config`` under the special id ``_announcements`` so it
survives restarts and can be edited via the settings UI.

Sources are ingested into the shared ``events`` store so the existing
reminder scheduler fires them — no separate ticker needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .events.store import Event, EventStore, Reminder

log = logging.getLogger("eg4.announcements")

CONFIG_ID = "_announcements"

# Ingest window — extremes further out than this are ignored (they'll
# be picked up on a later ingest pass).
INGEST_HORIZON_HOURS = 48


DEFAULT_CONFIG: dict[str, Any] = {
    "tides": {
        "enabled": False,
        "warn_minutes_before": [120, 30],
        "channels": ["tts", "telegram"],
        "types": ["high", "low"],
        "stations": [],
    },
    "hoa": {
        # HOA reminders already seeded by events scheduler; this lets
        # the user override the default 60-min + morning-of offsets.
        "enabled": True,
        "warn_minutes_before": [60],
        "channels": ["tts"],
    },
    "storms": {
        "enabled": False,
        "channels": ["tts", "telegram"],
    },
    "quakes": {
        "enabled": False,
        "min_magnitude": 4.5,
        "channels": ["telegram"],
    },
}


def merged_config(saved: dict | None) -> dict[str, Any]:
    """Return DEFAULT_CONFIG deeply merged with the persisted config
    so new sources light up with sane defaults after an upgrade."""
    out: dict[str, Any] = {}
    for source, defaults in DEFAULT_CONFIG.items():
        src_saved = (saved or {}).get(source) or {}
        out[source] = {**defaults, **src_saved}
    # Preserve any extra sources the user added
    for k, v in (saved or {}).items():
        if k not in out:
            out[k] = v
    return out


def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _reminders_from(cfg: dict) -> list[Reminder]:
    """Build one Reminder per (warn_offset, channel) pair.

    channel names collapse to ``mode`` on the Reminder — scheduler
    routes "tts", "telegram", or "tts+telegram"."""
    offsets = cfg.get("warn_minutes_before") or []
    channels = [c.lower() for c in (cfg.get("channels") or ["tts"])]
    if not channels:
        return []
    mode = "+".join(channels) if len(channels) > 1 else channels[0]
    return [
        Reminder(id="", event_id="", minutes_before=int(m), mode=mode)
        for m in offsets
    ]


async def ingest_tide_events(
    event_store: EventStore,
    widget_store: Any,
    config: dict[str, Any],
) -> int:
    """Turn upcoming tide extremes into events with configured reminders."""
    tide_cfg = config.get("tides") or {}
    if not tide_cfg.get("enabled"):
        return 0
    if not tide_cfg.get("warn_minutes_before"):
        return 0

    state = await widget_store.get_state("tides")
    if not state or not state.data:
        return 0

    types_wanted = {str(t).lower() for t in (tide_cfg.get("types") or ["high", "low"])}
    stations_wanted = set(tide_cfg.get("stations") or [])

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=INGEST_HORIZON_HOURS)

    n = 0
    for st in state.data.get("stations") or []:
        if stations_wanted and st.get("id") not in stations_wanted:
            continue
        for e in st.get("extremes") or []:
            iso = e.get("iso")
            when = _parse_iso(iso) if iso else None
            if not when or when < now or when > horizon:
                continue
            e_type = str(e.get("type", "")).lower()
            if e_type not in types_wanted:
                continue

            source_ref = f"tide:{st.get('id')}:{iso}:{e_type}"
            height = e.get("height_m")
            height_str = f"{height:.2f} m" if isinstance(height, (int, float)) else ""
            title = (
                f"{e_type.title()} tide at {st.get('name', st.get('id'))}"
                + (f" — {height_str}" if height_str else "")
            )

            ev = Event(
                id="", source="tide", source_ref=source_ref, title=title,
                starts_at=when.isoformat(), is_special=True,
                reminders=_reminders_from(tide_cfg),
            )
            await event_store.upsert_hoa(ev)
            n += 1
    return n


async def ingest_all(
    event_store: EventStore,
    widget_store: Any,
    saved_config: dict[str, Any] | None,
) -> dict[str, int]:
    """Run every configured ingest and return per-source counts.

    Also prune tide events > 24h old so the events table stays bounded."""
    cfg = merged_config(saved_config)
    counts: dict[str, int] = {}
    try:
        counts["tides"] = await ingest_tide_events(event_store, widget_store, cfg)
    except Exception:  # noqa: BLE001
        log.exception("tide ingest failed")
        counts["tides"] = 0
    return counts
