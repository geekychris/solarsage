"""Trip planner — synthesizer for "is it a good day to drive to the US?"

Combines cached state from ``drive_time``, ``border``, and ``weather``
into a single "go-score" for the next few days. The score factors in:
* total trip time = free-flow drive + worst current border wait
* weather (heat + cloud cover at peak driving hours)
* whether it's a Mexican holiday (banks/Pemex closed)

No external fetch — pure synthesizer.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


async def _read(widget_id: str) -> dict[str, Any] | None:
    from .store import WidgetStore
    db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
    state = await WidgetStore(db_path).get_state(widget_id)
    return (state.data or {}) if state and state.data else None


def _worst_wait(ports: list[dict[str, Any]]) -> int | None:
    best = None
    for p in ports:
        std = (p.get("pov") or {}).get("standard") or {}
        m = std.get("delay_minutes")
        if isinstance(m, int):
            best = m if best is None else max(best, m)
    return best


class TripPlannerWidget(Widget):
    id = "trip_planner"
    kind = "trip_planner"
    name = "Trip planner"
    description = (
        "Daily 'go-score' for a US run from San Felipe. Combines drive "
        "time + current border wait + weather + holiday calendar. Higher "
        "is better. Synthesizer — reads other widgets' cached state."
    )
    refresh_seconds = 30 * 60
    default_tab = "Travel"
    default_position = 5

    config_schema = {
        "type": "object",
        "properties": {
            "primary_route_id": {"type": "string"},
        },
    }
    default_config = {"primary_route_id": "sf_to_calexico_w"}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        drive = await _read("drive_time") or {}
        border = await _read("border") or {}
        weather = await _read("weather") or {}
        holidays = await _read("holidays") or {}

        route_id = config.get("primary_route_id") or "sf_to_calexico_w"
        route = next(
            (r for r in drive.get("routes") or [] if r.get("id") == route_id),
            None,
        )

        ports = border.get("ports") or []
        wait_min = _worst_wait(ports)

        # Score today + next 6 days
        days = []
        for d in (weather.get("daily") or [])[:7]:
            day_score = 100
            high = d.get("high")
            if high is not None and high > 100:
                day_score -= min(40, (high - 100) * 3)
            cloud = d.get("cloud_mean_pct")
            if cloud is not None and cloud > 70:
                day_score -= 5
            precip = d.get("precip_prob") or 0
            day_score -= int(precip * 0.3)
            # Holiday penalty (banks / Pemex closed → harder logistics)
            is_holiday = any(
                h.get("date") == d.get("date")
                for h in holidays.get("upcoming") or []
            )
            if is_holiday:
                day_score -= 25
            days.append({
                "date": d.get("date"),
                "high": d.get("high"),
                "feels_max": d.get("feels_max"),
                "cloud_mean_pct": d.get("cloud_mean_pct"),
                "precip_prob": d.get("precip_prob"),
                "is_holiday": is_holiday,
                "score": max(0, day_score),
            })

        total_min = None
        if route and route.get("ok") and isinstance(wait_min, int):
            total_min = round(route["duration_min"] + wait_min, 0)

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "primary_route": route,
            "current_border_wait_min": wait_min,
            "total_trip_min_today": total_min,
            "days": days,
            "note": (
                "Border wait component is right-now only; the daily scores "
                "below ignore the border for forecasted days."
            ),
        }
