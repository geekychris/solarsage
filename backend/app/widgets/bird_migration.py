"""Bird migration windows for the Baja / Sea of Cortez flyway.

Baja is on the Pacific Flyway; the Sea of Cortez is a critical
stopover for shorebirds, waterfowl, and seabirds. This widget calls
out which species are moving through in the current window based on
a static per-month lookup — no eBird API dependency (their token is
touchy about SolarSage-style low-traffic use).

For each currently-active migration or resident-plus-migrant peak,
returns the species, direction, and rough peak weeks. Bird nerds can
edit the calendar in the widget config to add local sightings.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .base import Widget

# One entry per species/window. ``months`` is 1-based; peak_month is
# the strongest window locally. Sources: iNaturalist Sea of Cortez
# checklist + Xantus family notes + El Vizcaíno biosphere reports.
DEFAULT_CALENDAR = [
    {"species": "Osprey",             "months": [1, 2, 3, 4, 10, 11, 12], "peak": 3,  "direction": "N",  "note": "Sf-northern breeders passing through; fishing docks in early morning."},
    {"species": "Peregrine falcon",   "months": [10, 11, 12, 1, 2, 3, 4], "peak": 11, "direction": "S",  "note": "Chase shorebirds along beaches."},
    {"species": "Gray whales (bonus)","months": [12, 1, 2, 3, 4],         "peak": 2,  "direction": "S→N", "note": "Not birds, but the same coast — southbound to Laguna Ojo de Liebre."},
    {"species": "Marbled godwit",     "months": [8, 9, 10, 11, 12, 1, 2, 3, 4], "peak": 11, "direction": "S", "note": "Long-billed shorebird flocks on mudflats near estuaries."},
    {"species": "Willets & whimbrels", "months": [8, 9, 10, 11, 12, 1, 2, 3, 4], "peak": 10, "direction": "S", "note": "Common on any sand or mud coastline."},
    {"species": "Blue-footed booby",  "months": [1, 2, 3, 4, 5, 10, 11, 12], "peak": 3, "direction": "resident", "note": "Endemic breeder — nesting rocks near Islas del Golfo."},
    {"species": "Brown pelican",      "months": list(range(1, 13)),      "peak": 4,  "direction": "resident", "note": "Year-round; plunge-diving at fishing hours."},
    {"species": "Yellow-footed gull", "months": list(range(1, 13)),      "peak": 6,  "direction": "Gulf endemic", "note": "Gulf of California-only species; large and vocal."},
    {"species": "Common loon",        "months": [11, 12, 1, 2, 3],       "peak": 1,  "direction": "S",  "note": "Winter visitor to the gulf."},
    {"species": "Elegant tern",       "months": [3, 4, 5, 6, 7, 8, 9],   "peak": 5,  "direction": "resident-breeder", "note": "Isla Rasa in the middle gulf holds ~95% of the world population."},
    {"species": "Northern shovelers", "months": [10, 11, 12, 1, 2, 3],   "peak": 1,  "direction": "S",  "note": "Estero de San José wetlands."},
    {"species": "Snow / Ross's geese","months": [11, 12, 1, 2],          "peak": 12, "direction": "S",  "note": "Big flocks — check flooded fields inland."},
]


class BirdMigrationWidget(Widget):
    id = "bird_migration"
    kind = "bird_migration"
    name = "Bird migration"
    description = (
        "Which birds are moving through the Sea of Cortez / Baja "
        "Pacific Flyway this month, plus a few resident specialties. "
        "Static local calendar — no external API. Edit the list in "
        "widget config to add species you spot locally."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Outdoor"
    default_position = 45

    config_schema = {
        "type": "object",
        "properties": {
            "calendar": {"type": "array"},
        },
    }
    default_config = {"calendar": DEFAULT_CALENDAR}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).astimezone()
        m = now.month
        calendar = config.get("calendar") or DEFAULT_CALENDAR

        active = []
        peaking = []
        for row in calendar:
            months = row.get("months") or []
            if m not in months:
                continue
            entry = {
                "species": row["species"],
                "peak_month": row.get("peak"),
                "direction": row.get("direction", ""),
                "note": row.get("note", ""),
                "months_active": months,
                "at_peak": row.get("peak") == m,
            }
            active.append(entry)
            if entry["at_peak"]:
                peaking.append(entry)

        return {
            "fetched_at": now.isoformat(),
            "month": m,
            "month_name": now.strftime("%B"),
            "active_count": len(active),
            "peaking_count": len(peaking),
            "active": active,
            "peaking": peaking,
        }
