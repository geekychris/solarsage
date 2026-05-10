"""Default appliance catalog seeded into new sites.

Each entry is a deferrable appliance candidate the scheduler may recommend
windows for. Users enable/disable per site (the user explicitly said they
don't have a pool pump but do have a water pump etc.).

Wattages are typical North American 120V/240V residential figures — adjust
per-site as needed via the appliances UI.
"""

DEFAULT_APPLIANCES = [
    # name, watts, typical_minutes, can_defer, preferred_start, preferred_end
    {"name": "Water pump (house)", "watts": 900, "typical_minutes": 15, "can_defer": 1},
    {"name": "Clothes washer", "watts": 500, "typical_minutes": 50, "can_defer": 1, "preferred_start_hour": 10, "preferred_end_hour": 16},
    {"name": "Dishwasher", "watts": 1500, "typical_minutes": 90, "can_defer": 1, "preferred_start_hour": 11, "preferred_end_hour": 15},
    {"name": "Air conditioning (boost)", "watts": 2200, "typical_minutes": 120, "can_defer": 1, "preferred_start_hour": 11, "preferred_end_hour": 15},
    {"name": "Computer workstation", "watts": 350, "typical_minutes": 480, "can_defer": 0},
    {"name": "Water heater (heat-up)", "watts": 4500, "typical_minutes": 60, "can_defer": 1, "preferred_start_hour": 10, "preferred_end_hour": 15},
    {"name": "EV charger (Level 2)", "watts": 7200, "typical_minutes": 180, "can_defer": 1, "preferred_start_hour": 10, "preferred_end_hour": 16},
    {"name": "Pool pump", "watts": 1100, "typical_minutes": 240, "can_defer": 1, "preferred_start_hour": 10, "preferred_end_hour": 16, "enabled": 0},
    {"name": "Clothes dryer (electric)", "watts": 3000, "typical_minutes": 45, "can_defer": 1, "enabled": 0},
]


def seed_for_site(site_id: str) -> list[dict]:
    """Return DEFAULT_APPLIANCES instances ready to insert for a site."""
    return [{**a, "site_id": site_id, "enabled": a.get("enabled", 1)} for a in DEFAULT_APPLIANCES]
