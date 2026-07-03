"""DAB e.syMINI water-pump stats widget.

Reads a suite of ``sensor.esyminiv2_*`` entities from Home Assistant
and surfaces the numbers a homeowner actually cares about — is the
pump running, what pressure is it holding, how much water and power
has it used, what mode is it in — plus enough plumbing detail (RPM,
current, heatsink temp) to spot failing hardware early.

Purely read-only. The companion ``dab_pump_control`` widget owns the
mode toggles.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

log = logging.getLogger("eg4.widgets.dab_pump")


async def _ha_state(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str, entity_id: str,
) -> tuple[Any, dict | None]:
    """Return (raw_state, attributes) or (None, None) on any error.

    Raw is the string HA returned. Caller decides whether to coerce.
    """
    if not entity_id:
        return None, None
    try:
        async with http.get(
            f"{ha_url}/api/states/{entity_id}",
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=10,
        ) as r:
            if r.status != 200:
                return None, None
            payload = await r.json()
    except Exception:
        return None, None
    return payload.get("state"), (payload.get("attributes") or {})


def _as_float(v: Any) -> float | None:
    if v in (None, "", "unknown", "unavailable"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v: Any) -> int | None:
    f = _as_float(v)
    return None if f is None else int(f)


class DabPumpWidget(Widget):
    id = "dab_pump"
    kind = "dab_pump"
    name = "Water pump"
    description = (
        "DAB e.syMINI pump telemetry from Home Assistant. Live status "
        "(Standby / Running), current + setpoint pressure, flow, power "
        "draw, RPM, heatsink temp, total gallons + kWh delivered, and "
        "which mode (Sleep / Power Shower) is active with its countdown."
    )
    refresh_seconds = 60
    default_tab = "House"
    default_position = 10

    ha_entities = [
        {"key": "status_eid",              "label": "Pump status",
         "domain": "sensor", "required": True},
        {"key": "pressure_eid",            "label": "Current pressure (psi)",
         "domain": "sensor", "required": True},
        {"key": "setpoint_eid",            "label": "Setpoint pressure (psi)",
         "domain": "number", "required": False},
        {"key": "flow_eid",                "label": "Flow (gal/min)",
         "domain": "sensor", "required": False},
        {"key": "power_eid",               "label": "Power draw (kW)",
         "domain": "sensor", "required": False},
        {"key": "rpm_eid",                 "label": "Pump RPM",
         "domain": "sensor", "required": False},
        {"key": "current_eid",             "label": "Phase current (A)",
         "domain": "sensor", "required": False},
        {"key": "temp_eid",                "label": "Heatsink temperature (°F)",
         "domain": "sensor", "required": False},
        {"key": "system_status_eid",       "label": "System status",
         "domain": "sensor", "required": False},
        {"key": "fault_count_eid",         "label": "Pumps in error",
         "domain": "sensor", "required": False},
        {"key": "running_count_eid",       "label": "Pumps running",
         "domain": "sensor", "required": False},
        {"key": "runtime_eid",             "label": "Pump run seconds",
         "domain": "sensor", "required": False},
        {"key": "starts_eid",              "label": "Start count",
         "domain": "sensor", "required": False},
        {"key": "total_gal_eid",           "label": "Total gallons delivered",
         "domain": "sensor", "required": False},
        {"key": "partial_gal_eid",         "label": "Partial gallons delivered",
         "domain": "sensor", "required": False},
        {"key": "period_gal_eid",          "label": "This period gallons",
         "domain": "sensor", "required": False},
        {"key": "total_energy_eid",        "label": "Total energy (kWh)",
         "domain": "sensor", "required": False},
        {"key": "period_energy_eid",       "label": "This period energy (kWh)",
         "domain": "sensor", "required": False},
        {"key": "saving_pct_eid",          "label": "Saving vs on/off (%)",
         "domain": "sensor", "required": False},
        {"key": "power_shower_target_eid", "label": "Power shower pressure (psi)",
         "domain": "sensor", "required": False},
        {"key": "power_shower_countdown_eid", "label": "Power shower countdown (s)",
         "domain": "sensor", "required": False},
        {"key": "sleep_target_eid",        "label": "Sleep mode pressure (psi)",
         "domain": "sensor", "required": False},
        {"key": "sleep_countdown_eid",     "label": "Sleep mode countdown (s)",
         "domain": "sensor", "required": False},
        {"key": "signal_eid",              "label": "Wi-Fi signal (%)",
         "domain": "sensor", "required": False},
    ]

    config_schema = {
        "type": "object",
        "properties": {k["key"]: {"type": "string"} for k in ha_entities},
    }

    # Defaults match the SF install (product serial 252700461191 →
    # entity slug esyminiv2_rhjl6). Users on other installs can retarget
    # via the Settings HA-integration UI.
    default_config = {
        "status_eid":                   "sensor.esyminiv2_rhjl6_pumpstatus",
        "pressure_eid":                 "sensor.esyminiv2_rhjl6_vp_pressurepsi",
        "setpoint_eid":                 "number.esyminiv2_rhjl6_sp_setpointpressurepsi",
        "flow_eid":                     "sensor.esyminiv2_rhjl6_vf_flowgall",
        "power_eid":                    "sensor.esyminiv2_rhjl6_grouppower",
        "rpm_eid":                      "sensor.esyminiv2_rhjl6_rs_rotatingspeed",
        "current_eid":                  "sensor.esyminiv2_rhjl6_c1_pumpphasecurrent",
        "temp_eid":                     "sensor.esyminiv2_rhjl6_te_heatsinktemperaturef",
        "system_status_eid":            "sensor.esyminiv2_rhjl6_systemstatus",
        "fault_count_eid":              "sensor.esyminiv2_rhjl6_faultpumpsnumber",
        "running_count_eid":            "sensor.esyminiv2_rhjl6_runningpumpsnumber",
        "runtime_eid":                  "sensor.esyminiv2_rhjl6_so_pumprunseconds",
        "starts_eid":                   "sensor.esyminiv2_rhjl6_startnumber",
        "total_gal_eid":                "sensor.esyminiv2_rhjl6_fct_total_delivered_flow_gall",
        "partial_gal_eid":              "sensor.esyminiv2_rhjl6_fcp_partial_delivered_flow_gall",
        "period_gal_eid":               "sensor.esyminiv2_rhjl6_actual_period_flow_counter_gall",
        "total_energy_eid":             "sensor.esyminiv2_rhjl6_totalenergy",
        "period_energy_eid":            "sensor.esyminiv2_rhjl6_actual_period_energy_counter",
        "saving_pct_eid":               "sensor.esyminiv2_rhjl6_saving",
        "power_shower_target_eid":      "sensor.esyminiv2_rhjl6_powershowerpressurepsi",
        "power_shower_countdown_eid":   "sensor.esyminiv2_rhjl6_powershowercountdown",
        "sleep_target_eid":             "sensor.esyminiv2_rhjl6_sleepmodepressurepsi",
        "sleep_countdown_eid":          "sensor.esyminiv2_rhjl6_sleepmodecountdown",
        "signal_eid":                   "sensor.esyminiv2_rhjl6_signlevel",
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        ha_url = os.getenv("HA_URL", "").rstrip("/")
        ha_token = os.getenv("HA_TOKEN")
        if not ha_url or not ha_token:
            raise RuntimeError("HA_URL + HA_TOKEN not set in backend/.env")

        eids = {k["key"]: (config.get(k["key"]) or "") for k in self.ha_entities}

        async with aiohttp.ClientSession() as http:
            reads = {}
            for key, eid in eids.items():
                state, _ = await _ha_state(http, ha_url, ha_token, eid)
                reads[key] = state

        status = reads.get("status_eid")
        system_status = reads.get("system_status_eid")
        running_count = _as_int(reads.get("running_count_eid"))
        fault_count = _as_int(reads.get("fault_count_eid"))

        # Sleep / Power-shower "is this mode active right now?" —
        # HA reports the sensor as ``unknown`` when the countdown isn't
        # running, and as an integer seconds value when it is.
        ps_countdown = _as_int(reads.get("power_shower_countdown_eid"))
        sleep_countdown = _as_int(reads.get("sleep_countdown_eid"))
        active_mode = None
        if ps_countdown and ps_countdown > 0:
            active_mode = "power_shower"
        elif sleep_countdown and sleep_countdown > 0:
            active_mode = "sleep"

        runtime_seconds = _as_int(reads.get("runtime_eid"))
        runtime_hours = None
        if runtime_seconds is not None:
            runtime_hours = round(runtime_seconds / 3600, 1)

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "status":         status,                       # 'Standby' / 'Running' / ...
            "system_status":  system_status,                # 'Ok' / fault code
            "running_count":  running_count,
            "fault_count":    fault_count,
            "active_mode":    active_mode,                  # 'power_shower' | 'sleep' | None
            "pressure_psi":       _as_float(reads.get("pressure_eid")),
            "setpoint_psi":       _as_float(reads.get("setpoint_eid")),
            "flow_gpm":           _as_float(reads.get("flow_eid")),
            "power_kw":           _as_float(reads.get("power_eid")),
            "rpm":                _as_int(reads.get("rpm_eid")),
            "current_a":          _as_float(reads.get("current_eid")),
            "heatsink_f":         _as_float(reads.get("temp_eid")),
            "runtime_seconds":    runtime_seconds,
            "runtime_hours":      runtime_hours,
            "starts":             _as_int(reads.get("starts_eid")),
            "total_gallons":      _as_int(reads.get("total_gal_eid")),
            "partial_gallons":    _as_int(reads.get("partial_gal_eid")),
            "period_gallons":     _as_int(reads.get("period_gal_eid")),
            "total_energy_kwh":   _as_float(reads.get("total_energy_eid")),
            "period_energy_kwh":  _as_float(reads.get("period_energy_eid")),
            "saving_pct":         _as_int(reads.get("saving_pct_eid")),
            "power_shower_target_psi":   _as_float(reads.get("power_shower_target_eid")),
            "power_shower_countdown_s":  ps_countdown,
            "sleep_target_psi":          _as_float(reads.get("sleep_target_eid")),
            "sleep_countdown_s":         sleep_countdown,
            "signal_pct":         _as_int(reads.get("signal_eid")),
        }
