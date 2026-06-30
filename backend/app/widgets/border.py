"""US-Mexico border wait times — CBP public XML feed.

The CBP feed at ``bwt.cbp.gov/xml/bwt.xml`` lists ~80 ports of entry. We
filter by configurable port_number list and surface the standard / SENTRI /
Ready Lane wait times for privately-owned-vehicle (POV) traffic.

Default port: 250302 (Calexico West POV), the closest crossing from
San Felipe heading north.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import Widget

CBP_XML_URL = "https://bwt.cbp.gov/xml/bwt.xml"


def _int_or_none(s: str | None) -> int | None:
    if s is None:
        return None
    s = s.strip()
    if not s or not s.lstrip("-").isdigit():
        return None
    return int(s)


def _lane_info(el: ET.Element | None) -> dict[str, Any] | None:
    if el is None:
        return None
    return {
        "operational_status": (el.findtext("operational_status") or "").strip(),
        "delay_minutes": _int_or_none(el.findtext("delay_minutes")),
        "lanes_open": _int_or_none(el.findtext("lanes_open")),
        "update_time": (el.findtext("update_time") or "").strip(),
    }


def _parse_port(p: ET.Element) -> dict[str, Any]:
    pv = p.find("passenger_vehicle_lanes")
    pov_lanes: dict[str, Any] = {}
    if pv is not None:
        pov_lanes = {
            "standard": _lane_info(pv.find("standard_lanes")),
            "nexus_sentri": _lane_info(pv.find("NEXUS_SENTRI_lanes")),
            "ready_lane": _lane_info(pv.find("ready_lanes")),
        }
    return {
        "port_number": (p.findtext("port_number") or "").strip(),
        "port_name": (p.findtext("port_name") or "").strip(),
        "crossing_name": (p.findtext("crossing_name") or "").strip(),
        "border": (p.findtext("border") or "").strip(),
        "port_status": (p.findtext("port_status") or "").strip(),
        "hours": (p.findtext("hours") or "").strip(),
        "pov": pov_lanes,
    }


class BorderWidget(Widget):
    id = "border"
    kind = "border"
    name = "Border wait times"
    description = (
        "US-Mexico border crossing wait times (CBP). Defaults to Calexico "
        "West POV — the natural crossing from San Felipe. Config "
        "``port_numbers`` accepts any port number from the CBP feed."
    )
    refresh_seconds = 15 * 60  # CBP updates every ~10-15 min

    data_schema = {
        "type": "object",
        "properties": {
            "fetched_at": {"type": "string", "format": "date-time"},
            "ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "port_number": {"type": "string"},
                        "port_name": {"type": "string"},
                        "crossing_name": {"type": "string"},
                        "port_status": {"type": "string"},
                        "hours": {"type": "string"},
                        "pov": {
                            "type": "object",
                            "properties": {
                                "standard":      {"type": "object"},
                                "nexus_sentri":  {"type": "object"},
                                "ready_lane":    {"type": "object"},
                            },
                        },
                    },
                },
            },
        },
    }

    config_schema = {
        "type": "object",
        "properties": {
            "port_numbers": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of CBP port_number values to display. "
                    "Common ones: 250302 (Calexico West), 250301 (Calexico "
                    "East), 250201 (Andrade), 260801 (San Luis I), "
                    "260802 (San Luis II), 250401 (San Ysidro)."
                ),
            },
        },
    }

    default_config = {"port_numbers": ["250302", "250301", "250201"]}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        wanted = set(config.get("port_numbers") or [])
        async with aiohttp.ClientSession() as http:
            async with http.get(
                CBP_XML_URL,
                timeout=30,
                headers={"User-Agent": "SolarSage/1.0 (border widget)"},
            ) as r:
                xml = await r.text()
        root = ET.fromstring(xml)
        ports = []
        for p in root.findall("port"):
            pn = (p.findtext("port_number") or "").strip()
            if not wanted or pn in wanted:
                ports.append(_parse_port(p))
        # Preserve user's configured order
        if wanted:
            order = {pn: i for i, pn in enumerate(config.get("port_numbers") or [])}
            ports.sort(key=lambda x: order.get(x["port_number"], 9999))
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": CBP_XML_URL,
            "ports": ports,
        }
