"""Meteor shower tracker.

The IMO (International Meteor Organization) publishes an annual
calendar with a stable set of showers. We ship the calendar embedded
so this widget doesn't need network access, and highlight the *next*
shower with its peak date + expected zenithal hourly rate (ZHR).

Once a shower's peak is within the ``announce_within_days`` window,
the widget publishes an event with reminders that get picked up by
the existing announcements framework — so you actually hear about
it before the peak, not the morning after.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget

# Yearly IMO calendar of the "worth-watching" showers. Peak dates are
# approximate (±1 day is normal); ZHR is peak activity. Ordered by
# peak date within a year.
SHOWERS = [
    {"name": "Quadrantids",        "peak_mm": 1,  "peak_dd": 3,  "zhr": 120, "hint": "Radiant near Boötes; north-facing sky, best before dawn."},
    {"name": "Lyrids",             "peak_mm": 4,  "peak_dd": 22, "zhr": 18,  "hint": "Fast bright meteors; late evening onward."},
    {"name": "Eta Aquariids",      "peak_mm": 5,  "peak_dd": 6,  "zhr": 50,  "hint": "Pre-dawn; low southern radiant — better for Baja than the US."},
    {"name": "Delta Aquariids",    "peak_mm": 7,  "peak_dd": 30, "zhr": 25,  "hint": "Steady rate for a week either side; low southern radiant."},
    {"name": "Perseids",           "peak_mm": 8,  "peak_dd": 12, "zhr": 100, "hint": "The big one. Nightlong show, best after midnight, north-east."},
    {"name": "Orionids",           "peak_mm": 10, "peak_dd": 21, "zhr": 20,  "hint": "Fast Halley debris; radiant near Orion."},
    {"name": "Leonids",            "peak_mm": 11, "peak_dd": 17, "zhr": 15,  "hint": "Occasional storm years; check IMO for the year's outlook."},
    {"name": "Geminids",           "peak_mm": 12, "peak_dd": 14, "zhr": 150, "hint": "The best of the year — meteors even at 8 pm. Look east."},
    {"name": "Ursids",             "peak_mm": 12, "peak_dd": 22, "zhr": 10,  "hint": "Minor but pleasant; near Ursa Minor."},
]


def _upcoming(now: date) -> list[dict[str, Any]]:
    """Return showers sorted by 'days until peak', wrapping across years."""
    out = []
    for sh in SHOWERS:
        peak = date(now.year, sh["peak_mm"], sh["peak_dd"])
        if peak < now:
            peak = date(now.year + 1, sh["peak_mm"], sh["peak_dd"])
        out.append({
            **sh,
            "peak_date": peak.isoformat(),
            "days_to_peak": (peak - now).days,
        })
    out.sort(key=lambda x: x["days_to_peak"])
    return out


class MeteorShowersWidget(Widget):
    id = "meteor_showers"
    kind = "meteor_showers"
    name = "Meteor showers"
    description = (
        "Upcoming annual meteor showers — peak date, expected ZHR "
        "(zenithal hourly rate), and viewing notes. The next shower is "
        "highlighted; when its peak is within the configured window "
        "the widget can publish an event so the announcements framework "
        "reminds you the day / hours before."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Outdoor"
    default_position = 27

    config_schema = {
        "type": "object",
        "properties": {
            "announce_within_days": {"type": "integer", "minimum": 0, "maximum": 30},
        },
    }
    default_config = {"announce_within_days": 3}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).date()
        upcoming = _upcoming(now)
        window = int(config.get("announce_within_days", 3))
        next_up = upcoming[0]
        next_up["within_announce_window"] = next_up["days_to_peak"] <= window

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "today": now.isoformat(),
            "next": next_up,
            "upcoming": upcoming[:5],
        }
