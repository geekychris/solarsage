"""Dedicated AC override widget.

A compact per-room chip grid: current on/off state, remaining override
window (if pinned), calibrated watts. Same read path as ``solar_vitals``
uses for AC (``input_boolean.ac_<room>`` + ``sensor.smart_ac_calibration``),
plus the per-room ``input_datetime.ac_<room>_override_until`` so the UI
can show "pinned until 22:00" without a second round-trip.

Writes go through the existing ``POST /api/smart_ac/override`` endpoint —
this widget only produces read state.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget
from .solar_vitals import _ha_entity


DEFAULT_ROOMS = ["master", "guest", "dining", "living", "office", "kyle"]


async def _fetch_room(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    room: str, per_room_watts: dict[str, int],
    per_room_note: dict[str, str], now_local: datetime,
) -> dict[str, Any]:
    """Read boolean + override_until for a single room."""
    bool_eid = f"input_boolean.ac_{room}"
    dt_eid = f"input_datetime.ac_{room}_override_until"

    bool_entity = await _ha_entity(http, ha_url, ha_token, bool_eid)
    dt_entity = await _ha_entity(http, ha_url, ha_token, dt_eid)

    state = str((bool_entity or {}).get("state") or "unknown").lower()

    override_until_iso: str | None = None
    override_minutes_left: int | None = None
    if dt_entity:
        dt_state = str(dt_entity.get("state") or "")
        # HA's input_datetime state comes back as "YYYY-MM-DD HH:MM:SS" (local).
        try:
            parsed = datetime.fromisoformat(dt_state.replace("T", " "))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now_local.tzinfo)
            if parsed.year > 1970 and parsed > now_local:
                override_until_iso = parsed.isoformat()
                override_minutes_left = int(
                    (parsed - now_local).total_seconds() // 60,
                )
        except ValueError:
            pass

    return {
        "room": room,
        "name": f"AC — {room.capitalize()}",
        "entity_id": bool_eid,
        "state": state,
        "on": state == "on",
        "watts": per_room_watts.get(room, 0),
        "note": per_room_note.get(room, "no calibration"),
        "override_until": override_until_iso,
        "override_minutes_left": override_minutes_left,
    }


class AcOverrideWidget(Widget):
    id = "ac_override"
    kind = "ac_override"
    name = "AC override"
    description = (
        "Compact override panel for the smart_ac scheduler. One chip per "
        "room, click to override with a preset duration (up to 10 hours) "
        "or pin until a specific date/time."
    )
    refresh_seconds = 60
    default_tab = "Solar"
    default_position = 4
    default_width = 2

    ha_entities = [
        {"key": "smart_ac_calibration_entity",
         "label": "smart_ac calibration sensor",
         "domain": "sensor", "required": False,
         "default": "sensor.smart_ac_calibration"},
    ]

    def ha_entities_for(self, config):
        entries = super().ha_entities_for(config)
        for room in config.get("rooms") or DEFAULT_ROOMS:
            entries.append({
                "key": f"ac_room:{room}",
                "label": f"AC — {room.capitalize()} (input_boolean)",
                "domain": "input_boolean",
                "required": False,
                "entity_id": f"input_boolean.ac_{room}",
                "read_only": True,
            })
            entries.append({
                "key": f"ac_room_override_until:{room}",
                "label": f"AC — {room.capitalize()} (override_until)",
                "domain": "input_datetime",
                "required": False,
                "entity_id": f"input_datetime.ac_{room}_override_until",
                "read_only": True,
            })
        return entries

    config_schema = {
        "type": "object",
        "properties": {
            "rooms": {"type": "array", "items": {"type": "string"}},
        },
    }
    default_config = {"rooms": list(DEFAULT_ROOMS)}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        rooms = config.get("rooms") or DEFAULT_ROOMS
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            return {"note": "HA_URL + HA_TOKEN not set", "rooms": []}

        now_local = datetime.now().astimezone()
        async with aiohttp.ClientSession() as http:
            # Calibration is one entity; fetch once and reuse across rooms.
            calibration = await _ha_entity(
                http, ha_url, ha_token, "sensor.smart_ac_calibration",
            )
            per_room_watts: dict[str, int] = {}
            per_room_note: dict[str, str] = {}
            if calibration:
                results = ((calibration.get("attributes") or {})
                           .get("results") or {})
                for room, info in results.items():
                    delta = (info or {}).get("delta_w")
                    if isinstance(delta, (int, float)) and delta > 0:
                        per_room_watts[room] = int(delta)
                    per_room_note[room] = str((info or {}).get("note") or "")

            # smart_ac_status.reasons gives us "why is this room off right now"
            status = await _ha_entity(
                http, ha_url, ha_token, "sensor.smart_ac_status",
            )
            reasons: dict[str, str] = {}
            mode: str | None = None
            if status:
                attrs = status.get("attributes") or {}
                mode = attrs.get("mode")
                reasons = attrs.get("reasons") or {}

            room_states = []
            for room in rooms:
                row = await _fetch_room(
                    http, ha_url, ha_token, room,
                    per_room_watts, per_room_note, now_local,
                )
                row["scheduler_reason"] = reasons.get(room, "")
                room_states.append(row)

        return {
            "fetched_at": now_local.isoformat(),
            "smart_ac_mode": mode,
            "rooms": room_states,
        }
