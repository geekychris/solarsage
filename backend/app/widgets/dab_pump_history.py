"""DAB e.syMINI water-pump delivery history.

Reads Home Assistant's ``/api/history/period`` for the pump's lifetime
totalizer sensor (``sensor.esyminiv2_rhjl6_fct_total_delivered_flow_gall``
by default) and rebuckets the state-change deltas into two series:

- ``by_hour`` — the last 24 hours, one bucket per hour, gallons delivered
- ``by_day``  — the last 7 days,  one bucket per day,  gallons delivered

HA's recorder only writes a row when the state changes, so idle hours
have no events at all. We carry-forward the last-known state to each
bucket boundary and take deltas across boundaries, which gives a
correct per-bucket volume even when the sensor is silent.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .base import Widget

log = logging.getLogger("eg4.widgets.dab_pump_history")


async def _ha_history(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    entity_id: str, start_iso: str, end_iso: str,
) -> list[dict]:
    """Return the raw state-change list HA gives us — [{state, last_changed}, …]."""
    params = {
        "filter_entity_id": entity_id,
        "end_time": end_iso,
        "minimal_response": "true",
        "no_attributes": "true",
    }
    try:
        async with http.get(
            f"{ha_url}/api/history/period/{start_iso}",
            params=params,
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=30,
        ) as r:
            if r.status != 200:
                return []
            payload = await r.json()
    except Exception:  # noqa: BLE001
        return []
    if not payload or not isinstance(payload, list) or not payload[0]:
        return []
    return payload[0]


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _samples(history: list[dict]) -> list[tuple[datetime, float]]:
    """Convert HA history rows into (datetime, float) sorted by time,
    dropping rows we can't parse."""
    out: list[tuple[datetime, float]] = []
    for h in history:
        raw_state = h.get("state")
        try:
            v = float(raw_state)
        except (TypeError, ValueError):
            continue
        ts = _parse_ts(h.get("last_changed") or h.get("last_updated"))
        if ts is None:
            continue
        out.append((ts, v))
    out.sort(key=lambda p: p[0])
    return out


def _value_at(samples: list[tuple[datetime, float]], t: datetime) -> float | None:
    """Last-known state at time ``t`` (i.e. the most recent sample with
    timestamp ≤ t). Binary-search would be nicer but N is ~2000; linear
    is fine and easier to audit."""
    last = None
    for ts, v in samples:
        if ts > t:
            break
        last = v
    return last


def _bucket_deltas(
    samples: list[tuple[datetime, float]],
    boundaries: list[datetime],
) -> list[float]:
    """Given ``N+1`` boundaries return ``N`` deltas: gallons delivered
    in each bucket. Negative deltas are clamped to 0 (would only happen
    if the totalizer resets)."""
    values = [_value_at(samples, b) for b in boundaries]
    # Any None values (boundaries older than the earliest sample) get
    # the earliest sample's value — the totalizer hadn't ticked past
    # that number yet, so treating the delta as 0 across those buckets
    # is the correct thing to say.
    if samples:
        earliest = samples[0][1]
        for i, v in enumerate(values):
            if v is None:
                values[i] = earliest
    deltas: list[float] = []
    for i in range(len(values) - 1):
        a, b = values[i], values[i + 1]
        if a is None or b is None:
            deltas.append(0.0)
        else:
            deltas.append(max(0.0, round(b - a, 2)))
    return deltas


class DabPumpHistoryWidget(Widget):
    id = "dab_pump_history"
    kind = "dab_pump_history"
    name = "Water use — history"
    description = (
        "Delivery volume by hour (last 24h) and by day (last 7d), "
        "computed from the pump's lifetime totalizer sensor. Answers "
        "'when do we actually use water?' — spot the shower spikes, "
        "the laundry runs, the irrigation windows."
    )
    refresh_seconds = 15 * 60
    default_tab = "House"
    default_position = 13
    default_width = 2

    ha_entities = [
        {"key": "totalizer_eid", "label": "Total gallons delivered",
         "domain": "sensor", "required": True},
    ]

    config_schema = {
        "type": "object",
        "properties": {
            "totalizer_eid": {"type": "string"},
        },
    }

    default_config = {
        "totalizer_eid": "sensor.esyminiv2_rhjl6_fct_total_delivered_flow_gall",
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            raise RuntimeError("HA_URL + HA_TOKEN not set in backend/.env")

        eid = (config.get("totalizer_eid") or "").strip()
        if not eid:
            raise RuntimeError("dab_pump_history: totalizer_eid not configured")

        now = datetime.now(timezone.utc)
        # 7d + a little slack so the earliest bucket has a baseline.
        start = now - timedelta(days=7, hours=2)

        async with aiohttp.ClientSession() as http:
            history = await _ha_history(
                http, ha_url, ha_token, eid,
                start.isoformat(), now.isoformat(),
            )

        samples = _samples(history)
        if not samples:
            return {
                "fetched_at": now.isoformat(),
                "entity_id":  eid,
                "note":       "No history returned by Home Assistant yet — "
                              "the recorder may still be warming up.",
                "by_hour": [], "by_day": [],
            }
        collected_since = samples[0][0].astimezone().isoformat()
        collected_hours = (now - samples[0][0]).total_seconds() / 3600

        # 24h × hourly. Buckets bounded to top-of-hour so the labels
        # line up cleanly with wall-clock (in the user's local zone).
        local_now = now.astimezone()
        hour_top  = local_now.replace(minute=0, second=0, microsecond=0)
        hourly_boundaries = [
            (hour_top - timedelta(hours=(24 - i))).astimezone(timezone.utc)
            for i in range(25)
        ]
        hourly_deltas = _bucket_deltas(samples, hourly_boundaries)
        by_hour = [
            {
                "start": hourly_boundaries[i].astimezone().isoformat(),
                "hour":  (hourly_boundaries[i].astimezone()).strftime("%-I%p").lower(),
                "gallons": hourly_deltas[i],
            }
            for i in range(24)
        ]

        # 7d × daily. Buckets bounded to local midnight.
        day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_boundaries = [
            (day_start - timedelta(days=(6 - i))).astimezone(timezone.utc)
            for i in range(8)
        ]
        # Include today-so-far so users see the running total.
        daily_boundaries[-1] = now
        daily_deltas = _bucket_deltas(samples, daily_boundaries)
        by_day = [
            {
                "start": daily_boundaries[i].astimezone().isoformat(),
                "label": (daily_boundaries[i].astimezone()).strftime("%a"),
                "gallons": daily_deltas[i],
            }
            for i in range(7)
        ]

        return {
            "fetched_at":       now.isoformat(),
            "entity_id":        eid,
            "collected_since":  collected_since,
            "collected_hours":  round(collected_hours, 1),
            "total_24h":        round(sum(hourly_deltas), 1),
            "total_7d":         round(sum(daily_deltas),  1),
            "avg_daily":        round(sum(daily_deltas) / 7, 1),
            "peak_hour":        max(by_hour, key=lambda x: x["gallons"]) if by_hour else None,
            "peak_day":         max(by_day,  key=lambda x: x["gallons"]) if by_day else None,
            "by_hour":          by_hour,
            "by_day":           by_day,
        }
