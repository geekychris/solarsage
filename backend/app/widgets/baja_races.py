"""SCORE International Baja race calendar.

Hard-coded near-term schedule so we don't depend on scraping bajaracing.
com every hour. Update ``EVENTS`` when new seasons drop.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


# id, name, start, end, involves_san_felipe, notes
EVENTS = [
    ("sf250_2026",   "SCORE San Felipe 250", "2026-03-06", "2026-03-08", True,
     "Starts + finishes in San Felipe — expect town lock-in."),
    ("baja500_2026", "SCORE Baja 500",       "2026-06-05", "2026-06-07", False,
     "Ensenada loop. HOA highlighted this one on the June calendar."),
    ("baja400_2026", "SCORE Baja 400",       "2026-09-24", "2026-09-26", False,
     "Ensenada."),
    ("baja1000_2026","SCORE Baja 1000",      "2026-11-19", "2026-11-22", True,
     "Ensenada → La Paz variant; peninsula run passes near San Felipe."),
    ("sf250_2027",   "SCORE San Felipe 250", "2027-03-05", "2027-03-07", True,
     "Provisional date; confirm with SCORE closer to season."),
]


class BajaRacesWidget(Widget):
    id = "baja_races"
    kind = "baja_races"
    name = "Baja races"
    description = (
        "SCORE International off-road race schedule. ★ marks events that "
        "involve San Felipe directly."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Community"
    default_position = 90

    config_schema = {"type": "object"}
    default_config = {}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        today = date.today()
        rows = []
        for eid, name, start, end, sf, notes in EVENTS:
            start_d = date.fromisoformat(start)
            end_d = date.fromisoformat(end)
            days_out = (start_d - today).days
            status = (
                "past" if end_d < today
                else "ongoing" if start_d <= today <= end_d
                else "upcoming"
            )
            rows.append({
                "id": eid, "name": name, "start": start, "end": end,
                "in_san_felipe": sf, "notes": notes,
                "status": status, "days_until": days_out,
            })
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "events": [r for r in rows if r["status"] != "past"],
            "past": [r for r in rows if r["status"] == "past"],
            "source": "https://score-international.com/",
        }
