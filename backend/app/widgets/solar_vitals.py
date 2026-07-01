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

import aiosqlite

from .base import Widget


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
        "appliances": [
            {"name": "Fridge",       "watts": 200,  "on": True},
            {"name": "AC — main",    "watts": 3500, "on": False},
            {"name": "AC — bedroom", "watts": 1500, "on": False},
            {"name": "Water heater", "watts": 4000, "on": False},
            {"name": "Pool pump",    "watts": 1000, "on": False},
            {"name": "EV charge",    "watts": 7000, "on": False},
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
        on_list = [
            {"name": a.get("name", "?"), "watts": float(a.get("watts", 0) or 0)}
            for a in appliances_cfg if a.get("on")
        ]
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
