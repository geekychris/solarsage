"""EG4 (monitor.eg4electronics.com) adapter."""

from __future__ import annotations

import os
from typing import Any

from eg4_inverter_api import EG4InverterAPI
from eg4_inverter_api.exceptions import EG4APIError, EG4AuthError

from ..eg4_history import fetch_day_lines
from .base import Inverter, SiteAdapter


class EG4Adapter(SiteAdapter):
    vendor = "eg4"

    def __init__(self, site_id, credentials, config):
        super().__init__(site_id, credentials, config)
        self._client: EG4InverterAPI | None = None
        self._inverters: list[Inverter] = []

    async def login(self) -> None:
        ignore_ssl = os.getenv("EG4_DISABLE_VERIFY_SSL", "0") == "1"
        base = self.config.get("base_url") or "https://monitor.eg4electronics.com"
        self._client = EG4InverterAPI(
            username=self.credentials["username"],
            password=self.credentials["password"],
            base_url=base,
        )
        try:
            await self._client.login(ignore_ssl=ignore_ssl)
        except (EG4AuthError, EG4APIError):
            raise
        self._inverters = []
        for inv in self._client.get_inverters():
            extra = {k: v for k, v in inv.__dict__.items() if not k.startswith("_")}
            self._inverters.append(Inverter(
                serial=inv.serialNum,
                plant_id=inv.plantId,
                plant_name=getattr(inv, "plantName", None),
                model=getattr(inv, "deviceTypeText", None) or getattr(inv, "modelText", None),
                extra=extra,
            ))

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def list_inverters(self) -> list[Inverter]:
        return list(self._inverters)

    def _select(self, serial: str) -> None:
        if self._client is None:
            raise RuntimeError("adapter not logged in")
        self._client.set_selected_inverter(serialNum=serial)

    async def runtime(self, serial: str) -> dict[str, Any]:
        self._select(serial)
        r = await self._client.get_inverter_runtime_async()
        return r.to_dict() if hasattr(r, "to_dict") else {}

    async def energy(self, serial: str) -> dict[str, Any]:
        self._select(serial)
        e = await self._client.get_inverter_energy_async()
        return e.to_dict() if hasattr(e, "to_dict") else {}

    async def battery(self, serial: str) -> dict[str, Any]:
        self._select(serial)
        b = await self._client.get_inverter_battery_async()
        return b.to_dict() if hasattr(b, "to_dict") else {}

    async def fetch_day(self, serial, date_text, tz_offset_minutes):
        if self._client is None:
            raise RuntimeError("adapter not logged in")
        samples = await fetch_day_lines(self._client, serial, date_text, tz_offset_minutes)
        return [(s.ts_ms, s.fields) for s in samples]
