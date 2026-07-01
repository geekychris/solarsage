"""Solar Vitals — glance-at-the-room summary of the solar system.

Answers the questions you actually ask a wall display:

    * Battery — % SoC + kWh remaining
    * Solar   — total production + per-string breakdown
    * Load    — house consumption (auto-detects across firmware variants;
                falls back to EPS phase sum when consumptionPower is 0
                on EPS-wired systems)
    * Rate    — pCharge / pDisCharge for the actual battery flow
    * When    — time to 100% or 0% at the current rate
    * Cut-back — projected time until the battery drops below a
                configurable SoC threshold (default 30%)
    * Today   — kWh produced / consumed / to-battery so far

Battery capacity is read from the live ``batCapacity`` sample (in Ah)
multiplied by the configured nominal voltage (default 51.2 V for the
standard EG4 lithium modules). Falls back to the ``settings`` table
setting ``battery_capacity_kwh`` if EG4 didn't report it.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import aiosqlite

from .base import Widget

DEFAULT_ON_STATES = ("on", "cool", "heat", "heat_cool", "auto",
                     "fan_only", "playing", "true", "yes")


async def _ha_entity(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    entity_id: str,
) -> dict | None:
    """Return the full entity dict (state + attributes) or None."""
    try:
        async with http.get(
            f"{ha_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=10,
        ) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception:
        return None


async def _fetch_smart_ac(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    rooms: list[str],
) -> list[dict]:
    """Query smart_ac_calibration + per-room booleans; return a list of
    ``{room, name, watts, on, note}`` — one per configured room."""
    calibration_entity = await _ha_entity(
        http, ha_url, ha_token, "sensor.smart_ac_calibration",
    )
    per_room_watts: dict[str, int] = {}
    per_room_note: dict[str, str] = {}
    if calibration_entity:
        results = ((calibration_entity.get("attributes") or {})
                   .get("results") or {})
        for room, info in results.items():
            note = str((info or {}).get("note") or "")
            delta = (info or {}).get("delta_w")
            if isinstance(delta, (int, float)) and delta > 0:
                per_room_watts[room] = int(delta)
                per_room_note[room] = note

    out = []
    for room in rooms:
        eid = f"input_boolean.ac_{room}"
        st = await _ha_entity(http, ha_url, ha_token, eid)
        state = str((st or {}).get("state") or "unknown").lower()
        watts = per_room_watts.get(room, 0)
        out.append({
            "room": room,
            "name": f"AC — {room.capitalize()}",
            "entity_id": eid,
            "watts": watts,
            "on": state == "on",
            "state": state,
            "note": per_room_note.get(room, "no calibration"),
        })
    return out


async def _resolve_ha_state(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    entity_id: str,
) -> str | None:
    """Return the current state of an HA entity, or None on error."""
    try:
        async with http.get(
            f"{ha_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=10,
        ) as r:
            if r.status != 200:
                return None
            payload = await r.json()
            return str(payload.get("state") or "").lower()
    except Exception:
        return None


def _appliance_is_on(state: str | None, on_states: list[str]) -> bool:
    """Match HA state against the appliance's on_states list."""
    if state is None or state in ("unavailable", "unknown", ""):
        return False
    on_states = [s.lower() for s in (on_states or DEFAULT_ON_STATES)]
    # Numeric threshold: "watts>=50" or ">=100"
    try:
        st_num = float(state)
    except (ValueError, TypeError):
        st_num = None
    for rule in on_states:
        rule = rule.strip()
        if rule.startswith(("watts>=", ">=")):
            threshold = float(rule.split(">=")[-1])
            if st_num is not None and st_num >= threshold:
                return True
        elif rule.startswith(("watts>", ">")):
            threshold = float(rule.split(">")[-1])
            if st_num is not None and st_num > threshold:
                return True
        elif rule == state.lower():
            return True
    return False


SOC_CANDIDATES  = ("soc", "unit0_soc", "batterySoc")
PV_TOTAL_CANDIDATES = ("ppv", "unit0_ppv", "solarPower")
PV_STRING_FIELDS = ("ppv1", "ppv2", "ppv3", "ppv4")
LOAD_CANDIDATES = (
    "consumptionPower",   # normal grid-tied
    "loadPower",
    "smartLoadPower",
    "unit0_load",
)
EPS_CANDIDATES = ("epsLoadPower", "peps")   # backup / EPS-wired systems
EPS_PHASE_FIELDS = ("pEpsL1N", "pEpsL2N")


async def _first_serial(db_path: str) -> str | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT DISTINCT serial_num FROM samples LIMIT 1")
        row = await cur.fetchone()
        return row[0] if row else None


async def _fields_for_serial(db_path: str, serial: str) -> set[str]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT field FROM samples WHERE serial_num=?", (serial,),
        )
        return {row[0] for row in await cur.fetchall()}


async def _latest(
    db_path: str, serial: str, field: str,
) -> tuple[float | None, int | None]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT ts, value FROM samples WHERE serial_num=? AND field=? "
            "ORDER BY ts DESC LIMIT 1",
            (serial, field),
        )
        row = await cur.fetchone()
    if not row:
        return None, None
    return float(row[1]), int(row[0])


async def _read_setting(db_path: str, key: str, default: float) -> float:
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
        if row and row[0] not in (None, ""):
            return float(row[0])
    except Exception:
        pass
    return default


def _pick_field(
    candidates: tuple[str, ...], available: set[str],
) -> str | None:
    for f in candidates:
        if f in available:
            return f
    return None


async def _latest_load_watts(
    db_path: str, serial: str, available: set[str],
) -> tuple[float | None, str | None]:
    """Return (load_watts, source_field_name).

    Tries fields in preferred order. EPS-wired systems report ``0`` on
    ``consumptionPower`` so we fall back to the phase sum in that case.
    """
    for f in LOAD_CANDIDATES:
        if f in available:
            v, _ = await _latest(db_path, serial, f)
            if v is not None and v > 5:
                return v, f
    for f in EPS_CANDIDATES:
        if f in available:
            v, _ = await _latest(db_path, serial, f)
            if v is not None and v > 5:
                return v, f
    total = 0.0
    any_hit = False
    for f in EPS_PHASE_FIELDS:
        if f in available:
            v, _ = await _latest(db_path, serial, f)
            if v is not None:
                any_hit = True
                total += v
    if any_hit:
        return total, "+".join(f for f in EPS_PHASE_FIELDS if f in available)
    for f in LOAD_CANDIDATES:
        if f in available:
            v, _ = await _latest(db_path, serial, f)
            if v is not None:
                return v, f
    return None, None


CAPACITY_CANDIDATES = ("fullCapacity", "batCapacity")


async def _capacity_kwh(
    db_path: str, serial: str, available: set[str], nominal_v: float,
    fallback_kwh: float,
) -> tuple[float, str]:
    """Prefer EG4's stored battery-bank capacity (Ah) × nominal
    voltage. Falls back to the settings row.

    The poller stores ``fullCapacity`` (the field EG4 exposes in the
    battery attribute block); older firmwares expose ``batCapacity``
    in the live snapshot but don't get polled — we try that too."""
    for f in CAPACITY_CANDIDATES:
        if f in available:
            ah, _ = await _latest(db_path, serial, f)
            if ah is not None and ah > 0:
                return ah * nominal_v / 1000.0, f"{f}={int(ah)}Ah × {nominal_v}V"
    return fallback_kwh, "settings.battery_capacity_kwh"


def _fmt_hours_minutes(hours: float) -> str:
    total_min = int(round(hours * 60))
    h, m = divmod(total_min, 60)
    if h == 0:
        return f"{m} min"
    if m == 0:
        return f"{h} h"
    return f"{h} h {m} min"


def _target_time_iso(hours: float) -> str:
    return (datetime.now().astimezone() + timedelta(hours=hours)).isoformat()


class SolarVitalsWidget(Widget):
    id = "solar_vitals"
    kind = "solar_vitals"
    name = "Solar vitals"
    description = (
        "Room-glance solar summary — SoC + kWh, per-string PV, house "
        "load (with heuristic breakdown), charge/discharge rate, "
        "projected time to full/empty, and cut-back warning. Auto-"
        "detects EG4 field names across firmware variants."
    )
    refresh_seconds = 60
    default_tab = "Solar"
    default_position = 3

    config_schema = {
        "type": "object",
        "properties": {
            "serial": {"type": ["string", "null"]},
            "cut_back_soc": {"type": "number"},
            "battery_nominal_voltage": {"type": "number"},
            "appliances": {"type": "array"},
        },
    }
    default_config = {
        "serial": None,
        "cut_back_soc": 30,
        "battery_nominal_voltage": 51.2,
        # When true, the widget also queries Home Assistant for the
        # smart_ac scheduler's per-room calibration + on/off state.
        # See docs/SMART_AC_INTEGRATION.md.
        "smart_ac_enabled": True,
        "smart_ac_rooms": ["master", "guest", "dining",
                            "living", "office", "kyle"],
        # When True, scale the sum of ON smart_ac rooms down to fit
        # the (load - manual) headroom. Prevents the pie showing
        # 6 kW of ACs when the inverter only reports 3 kW of load
        # (compressors cycle off between duty periods).
        "scale_smart_ac_to_load": True,
        # Each appliance may optionally link to a Home Assistant entity
        # (any domain — switch, sensor, binary_sensor, climate, etc.).
        # When ha_entity_id is set, the widget reads HA state on every
        # refresh and marks the appliance "on" automatically. When
        # blank the appliance is a manual toggle (tap on the card).
        #
        # ha_on_states lets you customise what counts as "on" —
        # defaults to any of ("on", "cool", "heat", "auto", "fan_only",
        # "playing"). For a numeric sensor (e.g. a power meter), set
        # ha_on_states=["watts>=50"] to interpret 50+ W as on.
        "appliances": [
            {"name": "Fridge",       "watts": 200,  "on": True},
            {"name": "Baseline",     "watts": 400,  "on": True},
        ],
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        serial = config.get("serial") or await _first_serial(db_path)
        if not serial:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "note": "no EG4 samples in history yet",
            }

        available = await _fields_for_serial(db_path, serial)
        nominal_v = float(config.get("battery_nominal_voltage", 51.2))
        fallback_kwh = await _read_setting(db_path, "battery_capacity_kwh", 14.3)
        capacity_kwh, capacity_source = await _capacity_kwh(
            db_path, serial, available, nominal_v, fallback_kwh,
        )
        cut_back_soc = float(config.get("cut_back_soc", 30))

        # SoC
        soc_field = _pick_field(SOC_CANDIDATES, available)
        soc_v, _ = (await _latest(db_path, serial, soc_field)) if soc_field else (None, None)

        # PV — total + per-string
        pv_total_field = _pick_field(PV_TOTAL_CANDIDATES, available)
        pv_v = None
        if pv_total_field:
            pv_v, _ = await _latest(db_path, serial, pv_total_field)
        strings: list[dict[str, Any]] = []
        pv_string_sum = 0.0
        for i, f in enumerate(PV_STRING_FIELDS, start=1):
            if f in available:
                v, _ = await _latest(db_path, serial, f)
                if v is not None:
                    strings.append({"n": i, "field": f, "watts": v})
                    pv_string_sum += v
        if pv_v is None and strings:
            pv_v = pv_string_sum
            pv_total_field = "sum(" + "+".join(s["field"] for s in strings) + ")"

        # Load
        load_v, load_field = await _latest_load_watts(db_path, serial, available)

        # Battery flow — explicit pCharge / pDisCharge preferred
        p_charge_w = p_discharge_w = None
        if "pCharge" in available:
            p_charge_w, _ = await _latest(db_path, serial, "pCharge")
        if "pDisCharge" in available:
            p_discharge_w, _ = await _latest(db_path, serial, "pDisCharge")

        # Grid flow
        to_grid_w = to_user_w = None
        if "pToGrid" in available:
            to_grid_w, _ = await _latest(db_path, serial, "pToGrid")
        if "pToUser" in available:
            to_user_w, _ = await _latest(db_path, serial, "pToUser")

        # Today's kWh totals
        today: dict[str, float] = {}
        for f in ("todayYielding", "todayCharging", "todayDischarging",
                  "todayUsage", "todayExport", "todayImport"):
            if f in available:
                v, _ = await _latest(db_path, serial, f)
                if v is not None:
                    today[f] = v

        # -------- Rate + state --------
        pv_kw       = (pv_v      / 1000) if pv_v      is not None else None
        load_kw     = (load_v    / 1000) if load_v    is not None else None
        charge_kw    = (p_charge_w    or 0) / 1000
        discharge_kw = (p_discharge_w or 0) / 1000

        state = "steady"
        if charge_kw > 0.05:
            state = "charging"
        elif discharge_kw > 0.05:
            state = "discharging"

        # -------- Projections (using ACTUAL capacity + charge rate) --------
        projection: dict[str, Any] | None = None
        if soc_v is not None and state != "steady":
            if state == "charging" and soc_v < 100 and charge_kw > 0.05:
                remaining_kwh = ((100 - soc_v) / 100.0) * capacity_kwh
                hours = remaining_kwh / charge_kw
                projection = {
                    "direction": "charging",
                    "rate_kw": round(charge_kw, 2),
                    "remaining_kwh": round(remaining_kwh, 2),
                    "hours": round(hours, 2),
                    "pretty": _fmt_hours_minutes(hours),
                    "target_at": _target_time_iso(hours),
                    "target_soc": 100,
                }
            elif state == "discharging" and soc_v > 0 and discharge_kw > 0.05:
                remaining_kwh = (soc_v / 100.0) * capacity_kwh
                hours = remaining_kwh / discharge_kw
                projection = {
                    "direction": "discharging",
                    "rate_kw": round(discharge_kw, 2),
                    "remaining_kwh": round(remaining_kwh, 2),
                    "hours": round(hours, 2),
                    "pretty": _fmt_hours_minutes(hours),
                    "target_at": _target_time_iso(hours),
                    "target_soc": 0,
                }

        cut_back: dict[str, Any] | None = None
        if (soc_v is not None and state == "discharging"
                and discharge_kw > 0.05 and soc_v > cut_back_soc):
            hours = ((soc_v - cut_back_soc) / 100.0) * capacity_kwh / discharge_kw
            cut_back = {
                "target_soc": cut_back_soc,
                "hours": round(hours, 2),
                "pretty": _fmt_hours_minutes(hours),
                "at": _target_time_iso(hours),
            }

        # -------- Load breakdown --------
        appliances_cfg = list(config.get("appliances") or [])

        # For each appliance with an HA entity, ask HA what state it's
        # in. That answer overrides the manual `on` field.
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        ha_states: dict[str, str | None] = {}
        smart_ac_rooms: list[dict] = []
        if ha_url and ha_token:
            async with aiohttp.ClientSession() as http:
                targets = [
                    a["ha_entity_id"] for a in appliances_cfg
                    if a.get("ha_entity_id")
                ]
                for eid in targets:
                    ha_states[eid] = await _resolve_ha_state(
                        http, ha_url, ha_token, eid,
                    )
                # smart_ac integration — pulls per-room delta_w from
                # sensor.smart_ac_calibration + input_boolean.ac_<room>
                # for on/off. See docs/SMART_AC_INTEGRATION.md.
                if config.get("smart_ac_enabled", True):
                    # Fall back to the six known rooms so users with a
                    # widget_config saved before smart_ac defaults were
                    # added still get live per-AC data.
                    rooms = config.get("smart_ac_rooms") or [
                        "master", "guest", "dining", "living", "office", "kyle",
                    ]
                    smart_ac_rooms = await _fetch_smart_ac(
                        http, ha_url, ha_token, rooms,
                    )

        on_list = []
        for a in appliances_cfg:
            watts = float(a.get("watts", 0) or 0)
            name = a.get("name", "?")
            eid = a.get("ha_entity_id") or ""
            source = "manual"
            is_on = bool(a.get("on"))
            if eid:
                st = ha_states.get(eid)
                is_on = _appliance_is_on(st, a.get("ha_on_states") or [])
                source = f"ha:{eid}={st or 'unavailable'}"
            if is_on:
                on_list.append({
                    "name": name, "watts": watts,
                    "ha_entity_id": eid or None,
                    "source": source,
                })
        # Collect smart_ac rooms that are currently ON with a rated
        # wattage — the "rated" figure is compressor-running draw, but
        # compressors cycle off when the setpoint is met, so instant
        # draw is usually lower than the sum-of-rated. Scale the ACs
        # proportionally to fit the space left after manual appliances.
        manual_sum = sum(a["watts"] for a in on_list)
        ac_candidates = [
            {"name": r["name"],
             "rated_watts": float(r["watts"]),
             "entity_id": r["entity_id"]}
            for r in smart_ac_rooms
            if r.get("on") and r.get("watts", 0) > 0
        ]
        ac_rated_sum = sum(c["rated_watts"] for c in ac_candidates)

        ac_scale = 1.0
        scale_acs = bool(config.get("scale_smart_ac_to_load", True))
        if (scale_acs and load_v is not None and ac_rated_sum > 0):
            remaining = max(0.0, load_v - manual_sum)
            if remaining < ac_rated_sum:
                ac_scale = remaining / ac_rated_sum

        for c in ac_candidates:
            shown = c["rated_watts"] * ac_scale
            on_list.append({
                "name": c["name"],
                "watts": round(shown, 1),
                "ha_entity_id": c["entity_id"],
                "source": "smart_ac",
                "rated_watts": round(c["rated_watts"]),
                "scale": round(ac_scale, 3),
            })

        # Stamp scaled figure back onto each room so the chip row shows
        # the same "shown" watts as the pie slice.
        for r in smart_ac_rooms:
            if r.get("on") and r.get("watts", 0) > 0:
                r["rated_watts"] = int(r["watts"])
                r["watts"] = round(r["watts"] * ac_scale, 1)
                r["scale"] = round(ac_scale, 3)

        sum_est_w = sum(a["watts"] for a in on_list)
        breakdown = list(on_list)
        if load_v is not None:
            diff = load_v - sum_est_w
            if diff > 30:
                breakdown.append({"name": "Unaccounted", "watts": round(diff)})
            elif diff < -30:
                breakdown.append({
                    "name": "Over-estimated",
                    "watts": round(abs(diff)),
                    "negative": True,
                })

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "serial": serial,
            "battery": {
                "soc": soc_v,
                "capacity_kwh": round(capacity_kwh, 2),
                "capacity_source": capacity_source,
                "kwh_used":      None if soc_v is None else round((soc_v / 100) * capacity_kwh, 2),
                "kwh_remaining": None if soc_v is None else round(((100 - soc_v) / 100) * capacity_kwh, 2),
            },
            "solar": {
                "total_kw": round(pv_kw, 2) if pv_kw is not None else None,
                "total_field": pv_total_field,
                "strings": [
                    {"n": s["n"], "kw": round(s["watts"] / 1000, 2)}
                    for s in strings
                ],
            },
            "load": {
                "kw": round(load_kw, 2) if load_kw is not None else None,
                "field": load_field,
                "breakdown": [
                    {**b, "kw": round(b["watts"] / 1000, 2)} for b in breakdown
                ],
                "estimated_on_kw": round(sum_est_w / 1000, 2),
                # Full appliance list with resolved on-state (so the UI
                # can show every appliance's button + which are HA-
                # controlled vs manual). Empty when no appliances
                # configured.
                "appliances": [
                    {
                        "name": a.get("name", "?"),
                        "watts": float(a.get("watts", 0) or 0),
                        "manual_on": bool(a.get("on")),
                        "ha_entity_id": a.get("ha_entity_id") or None,
                        "ha_state": ha_states.get(a.get("ha_entity_id") or ""),
                        "on": next(
                            (True for o in on_list if o["name"] == a.get("name")),
                            False,
                        ),
                        "source": (
                            f"ha:{a['ha_entity_id']}"
                            if a.get("ha_entity_id") else "manual"
                        ),
                    }
                    for a in appliances_cfg
                ],
                # smart_ac subsystem: per-room live state + calibrated
                # watts, whether ON or OFF (so the UI can show all six
                # ACs even when only some are running).
                "smart_ac_rooms": smart_ac_rooms,
            },
            "battery_flow": {
                "charge_kw":    round(charge_kw, 2),
                "discharge_kw": round(discharge_kw, 2),
                "state":        state,
            },
            "grid": {
                "to_grid_kw":   round((to_grid_w or 0) / 1000, 2),
                "from_grid_kw": round((to_user_w or 0) / 1000, 2),
            },
            "projection": projection,
            "cut_back": cut_back,
            "today": today,
            "fields_used": {
                "soc": soc_field, "pv_total": pv_total_field,
                "load": load_field, "capacity": capacity_source,
            },
        }
