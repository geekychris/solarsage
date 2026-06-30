"""Tide-corrected fishing window — synthesizer widget.

Reads the cached state of three other widgets (``tides``, ``sun_moon``,
``marine``) and combines them into a per-hour score for today, then
returns the top-N windows. No external API call of its own.

Scoring rules (heuristic):
* Tide change-rate is the biggest factor — fish move when the tide is
  moving. We compute the slope between adjacent high/low extremes.
* Dawn / dusk windows get a bonus.
* Calm seas (low wave height, low wind) score better.
* Score is clamped to [0, 100] for display.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .base import Widget


async def _read(widget_id: str) -> dict[str, Any] | None:
    # Lazy import keeps the test surface light.
    from .store import WidgetStore
    db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
    state = await WidgetStore(db_path).get_state(widget_id)
    return (state.data or {}) if state and state.data else None


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _tide_rate(extremes: list[dict[str, Any]], target: datetime) -> float:
    """Approximate |dh/dt| (m/h) at ``target`` by linear interpolation
    between the surrounding extremes."""
    if not extremes:
        return 0.0
    pairs = sorted(
        ((_parse_iso(e["iso"]), e["height_m"]) for e in extremes if e.get("iso")),
        key=lambda p: p[0],
    )
    for (t1, h1), (t2, h2) in zip(pairs, pairs[1:]):
        if t1 <= target <= t2:
            dt_h = (t2 - t1).total_seconds() / 3600.0
            return abs(h2 - h1) / dt_h if dt_h else 0.0
    return 0.0


class FishingWindowWidget(Widget):
    id = "fishing_window"
    kind = "fishing_window"
    name = "Fishing windows"
    description = (
        "Best fishing windows today / tomorrow based on tide movement, "
        "dawn/dusk light, and sea state. Pure synthesizer — reads cached "
        "data from the tides, sun_moon, and marine widgets, no external "
        "fetch."
    )
    refresh_seconds = 60 * 60
    default_tab = "Outdoor"
    default_position = 25

    config_schema = {
        "type": "object",
        "properties": {
            "tides_station_id": {"type": "string"},
            "top_n": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    }
    default_config = {"tides_station_id": "san_felipe", "top_n": 4}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        tides = await _read("tides") or {}
        sun_moon = await _read("sun_moon") or {}
        marine = await _read("marine") or {}

        station_id = config.get("tides_station_id") or "san_felipe"
        station = next(
            (s for s in tides.get("stations") or []
             if s.get("id") == station_id), None,
        )
        if not station:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "note": (
                    f"station {station_id!r} not in tide widget data; "
                    "configure the tides widget first"
                ),
                "windows": [],
            }
        extremes = station.get("extremes") or []
        sunrise_iso = (sun_moon.get("today") or {}).get("sunrise")
        sunset_iso = (sun_moon.get("today") or {}).get("sunset")
        sunrise = _parse_iso(sunrise_iso) if sunrise_iso else None
        sunset = _parse_iso(sunset_iso) if sunset_iso else None

        marine_h = {row["time"]: row for row in marine.get("hourly") or []}

        # Score each hour today
        local = datetime.now().astimezone()
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        scored = []
        for h in range(24):
            t = start + timedelta(hours=h)
            t_utc = t.astimezone(timezone.utc)
            tide_score = min(_tide_rate(extremes, t_utc) * 30, 60)  # 2 m/h → 60
            # Dawn/dusk bonus: within 90 min of sunrise / sunset
            light_score = 0
            for ref in (sunrise, sunset):
                if ref is None:
                    continue
                delta_min = abs((t_utc - ref).total_seconds()) / 60.0
                if delta_min < 90:
                    light_score = max(light_score, 20 * (1 - delta_min / 90))
            # Sea-state penalty
            iso_local = t.replace(tzinfo=None).isoformat(timespec="minutes")
            m_row = marine_h.get(iso_local) or {}
            wave = m_row.get("wave_height_m") or 0
            wind = m_row.get("wind_kn") or 0
            sea_penalty = wave * 8 + wind * 0.3
            score = max(0, min(100, tide_score + light_score - sea_penalty))
            scored.append({
                "time": t.isoformat(),
                "score": round(score, 1),
                "tide_rate_m_per_h": round(_tide_rate(extremes, t_utc), 3),
                "wave_height_m": m_row.get("wave_height_m"),
                "wind_kn": m_row.get("wind_kn"),
            })

        top_n = int(config.get("top_n", 4))
        windows = sorted(scored, key=lambda r: r["score"], reverse=True)[:top_n]
        windows.sort(key=lambda r: r["time"])

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "station": station_id,
            "sunrise": sunrise_iso,
            "sunset": sunset_iso,
            "hourly": scored,
            "best_windows": windows,
        }
