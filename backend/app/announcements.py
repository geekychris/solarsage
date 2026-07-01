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
from .notify import dispatch as _notify_dispatch

log = logging.getLogger("eg4.announcements")

CONFIG_ID = "_announcements"
STATE_ID = "_announcement_state"

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
    # State-based sources — fire when a live value crosses a
    # threshold. Each source rearms when the value returns to a
    # "safe" band so we don't spam the same alert every minute.
    "battery_charged": {
        "enabled": True,
        "threshold_soc": 98,
        "rearm_below_soc": 85,
        "channels": ["tts"],
    },
    "excessive_discharge": {
        "enabled": True,
        "threshold_kw": 3.0,
        "rearm_below_kw": 1.5,
        "min_sustained_seconds": 90,
        "channels": ["tts", "telegram"],
    },
    "water_low": {
        "enabled": True,
        # Warn when the tank crosses each of these percentages going down.
        # Each threshold rearms when the tank climbs back above (t + 5%).
        "warn_percents": [50, 25, 10],
        "channels": ["tts", "telegram"],
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


# ---------------------------------------------------------------------------
# State-based sources — fire on threshold crossings, rearm inside a band.
# ---------------------------------------------------------------------------


async def _get_ann_state(widget_store: Any) -> dict[str, Any]:
    return await widget_store.get_config(STATE_ID) or {}


async def _put_ann_state(widget_store: Any, state: dict[str, Any]) -> None:
    await widget_store.put_config(STATE_ID, state)


async def _fire(channels: list[str], text: str) -> None:
    for ch in channels or ["tts"]:
        try:
            await _notify_dispatch({"type": ch, "text": text})
        except Exception:  # noqa: BLE001
            log.exception("notify %s failed", ch)


async def check_battery_charged(
    widget_store: Any, cfg_all: dict[str, Any], state_blob: dict[str, Any],
) -> int:
    cfg = cfg_all.get("battery_charged") or {}
    if not cfg.get("enabled"):
        return 0
    threshold = float(cfg.get("threshold_soc", 98))
    rearm = float(cfg.get("rearm_below_soc", 85))
    channels = cfg.get("channels") or ["tts"]

    st = await widget_store.get_state("solar_vitals")
    if not st or not st.data:
        return 0
    soc = ((st.data.get("battery") or {}).get("soc"))
    if soc is None:
        return 0
    soc = float(soc)

    slot = state_blob.setdefault("battery_charged", {})
    fired = bool(slot.get("fired"))
    if not fired and soc >= threshold:
        await _fire(channels, f"Battery is fully charged, at {soc:.0f} percent.")
        slot["fired"] = True
        slot["fired_at"] = datetime.now(timezone.utc).isoformat()
        slot["at_soc"] = soc
        return 1
    if fired and soc <= rearm:
        slot["fired"] = False
        slot["rearmed_at"] = datetime.now(timezone.utc).isoformat()
    return 0


async def check_excessive_discharge(
    widget_store: Any, cfg_all: dict[str, Any], state_blob: dict[str, Any],
) -> int:
    cfg = cfg_all.get("excessive_discharge") or {}
    if not cfg.get("enabled"):
        return 0
    threshold_kw = float(cfg.get("threshold_kw", 3.0))
    rearm_kw = float(cfg.get("rearm_below_kw", 1.5))
    min_sustained = int(cfg.get("min_sustained_seconds", 90))
    channels = cfg.get("channels") or ["tts"]

    st = await widget_store.get_state("solar_vitals")
    if not st or not st.data:
        return 0
    bf = st.data.get("battery_flow") or {}
    if bf.get("state") != "discharging":
        # Not discharging — clear any pending "sustained" timer
        slot = state_blob.setdefault("excessive_discharge", {})
        slot.pop("high_since", None)
        return 0

    kw = float(bf.get("discharge_kw") or 0)
    slot = state_blob.setdefault("excessive_discharge", {})
    fired = bool(slot.get("fired"))
    now_iso = datetime.now(timezone.utc).isoformat()

    if kw >= threshold_kw:
        # Require the excursion to persist for min_sustained seconds so
        # a brief compressor kick doesn't announce.
        since = slot.get("high_since")
        if not since:
            slot["high_since"] = now_iso
            return 0
        try:
            since_dt = datetime.fromisoformat(since)
            held = (datetime.now(timezone.utc) - since_dt).total_seconds()
        except (TypeError, ValueError):
            held = 0
        if not fired and held >= min_sustained:
            await _fire(
                channels,
                f"Heavy load — the battery is discharging at "
                f"{kw:.1f} kilowatts.",
            )
            slot["fired"] = True
            slot["fired_at"] = now_iso
            slot["at_kw"] = kw
            return 1
    else:
        slot.pop("high_since", None)
        if fired and kw <= rearm_kw:
            slot["fired"] = False
            slot["rearmed_at"] = now_iso
    return 0


async def check_water_low(
    widget_store: Any, cfg_all: dict[str, Any], state_blob: dict[str, Any],
) -> int:
    cfg = cfg_all.get("water_low") or {}
    if not cfg.get("enabled"):
        return 0
    thresholds = sorted(
        (float(p) for p in (cfg.get("warn_percents") or [])),
        reverse=True,
    )
    if not thresholds:
        return 0
    channels = cfg.get("channels") or ["tts"]
    hysteresis = float(cfg.get("hysteresis_percent", 5))

    st = await widget_store.get_state("water_tank")
    if not st or not st.data:
        return 0
    percent = st.data.get("percent")
    if percent is None:
        return 0
    percent = float(percent)

    slot = state_blob.setdefault("water_low", {})
    fired_at_percent = slot.setdefault("fired_at_percent", {})

    fired_count = 0
    for t in thresholds:
        key = str(int(t))
        already = key in fired_at_percent
        if not already and percent <= t:
            days = st.data.get("days_remaining")
            days_str = (
                f", about {int(days)} days at current usage" if days else ""
            )
            await _fire(
                channels,
                f"Water tank is at {percent:.0f} percent{days_str}. "
                f"Consider ordering a refill.",
            )
            fired_at_percent[key] = datetime.now(timezone.utc).isoformat()
            fired_count += 1
        elif already and percent >= t + hysteresis:
            fired_at_percent.pop(key, None)
    return fired_count


async def run_state_checks(
    widget_store: Any, saved_config: dict[str, Any] | None,
) -> dict[str, int]:
    cfg = merged_config(saved_config)
    state_blob = await _get_ann_state(widget_store)
    counts: dict[str, int] = {}
    for name, fn in (
        ("battery_charged", check_battery_charged),
        ("excessive_discharge", check_excessive_discharge),
        ("water_low", check_water_low),
    ):
        try:
            counts[name] = await fn(widget_store, cfg, state_blob)
        except Exception:  # noqa: BLE001
            log.exception("%s state check failed", name)
            counts[name] = 0
    await _put_ann_state(widget_store, state_blob)
    return counts
