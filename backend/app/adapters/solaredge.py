"""SolarEdge monitoring API adapter.

Uses the official, documented REST API at https://monitoringapi.solaredge.com/.
Auth is a per-account API key — generate it from monitoring.solaredge.com →
Admin → Site Access → API Access. Credentials shape:
  {"api_key": "...", "site_id": "12345"}

Free for personal use. Rate-limited to 300 requests/day per site by default
(but ample for our 1-call-per-day backfill + per-minute live use).

Endpoints used:
  GET /site/{siteId}/currentPowerFlow.json
      live PV / load / grid / battery in watts, plus SOC
  GET /site/{siteId}/energyDetails        (resolution=QUARTER_OF_AN_HOUR)
      15-minute power across a date range
  GET /site/{siteId}/overview.json
      daily / month / year / lifetime energy totals
  GET /site/{siteId}/inventory.json
      panels / inverters / batteries on the site
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .base import Inverter, SiteAdapter

log = logging.getLogger("solarsage.solaredge")

BASE = "https://monitoringapi.solaredge.com"


class SolarEdgeAdapter(SiteAdapter):
    vendor = "solaredge"

    def __init__(self, site_id, credentials, config):
        super().__init__(site_id, credentials, config)
        self._api_key: str | None = credentials.get("api_key")
        self._se_site_id: str | None = str(credentials.get("site_id") or config.get("site_id") or "")
        self._inventory_cache: dict[str, Any] | None = None
        self._inverters: list[Inverter] = []
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                ssl=not (os.getenv("EG4_DISABLE_VERIFY_SSL", "0") == "1")
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        s = await self._get_session()
        p = {"api_key": self._api_key, **(params or {})}
        url = f"{BASE}{path}"
        async with s.get(url, params=p) as r:
            text = await r.text()
            if r.status != 200:
                raise RuntimeError(f"solaredge {path} -> HTTP {r.status}: {text[:300]}")
            import json as _json
            try:
                return _json.loads(text)
            except _json.JSONDecodeError as exc:
                raise RuntimeError(f"solaredge {path} returned non-JSON: {text[:200]}") from exc

    async def login(self) -> None:
        if not self._api_key or not self._se_site_id:
            raise RuntimeError("solaredge needs api_key + site_id in credentials")
        # Validate by hitting inventory; cache for later list_inverters()
        inv = await self._get(f"/site/{self._se_site_id}/inventory.json")
        self._inventory_cache = inv.get("Inventory") or {}
        self._inverters = []
        for i, item in enumerate(self._inventory_cache.get("inverters") or []):
            self._inverters.append(Inverter(
                serial=item.get("SN") or item.get("serialNumber") or f"se-{i}",
                plant_id=self._se_site_id,
                plant_name=self.config.get("name"),
                model=item.get("model"),
                extra=item,
            ))
        if not self._inverters:
            # Some sites surface only via siteId, not per-inverter — add a virtual one
            self._inverters.append(Inverter(
                serial=f"site-{self._se_site_id}",
                plant_id=self._se_site_id,
                plant_name=self.config.get("name"),
                model="SolarEdge site",
                extra={},
            ))

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def list_inverters(self) -> list[Inverter]:
        return list(self._inverters)

    async def runtime(self, serial: str) -> dict[str, Any]:
        """`currentPowerFlow.json` is the per-second live view."""
        data = await self._get(f"/site/{self._se_site_id}/currentPowerFlow.json")
        flow = data.get("siteCurrentPowerFlow") or {}
        out: dict[str, Any] = {}
        # Power values come as kW; convert to W to match the rest of the app
        for key in ("PV", "LOAD", "GRID", "STORAGE"):
            blk = flow.get(key) or {}
            w = blk.get("currentPower")
            if isinstance(w, (int, float)):
                out[f"{key.lower()}_w"] = w * 1000
        # Battery SoC is reported on STORAGE.chargeLevel as %
        storage = flow.get("STORAGE") or {}
        if storage.get("chargeLevel") is not None:
            out["soc"] = float(storage["chargeLevel"])
        if storage.get("status"):
            out["statusText"] = storage["status"]
        # Map to SolarSage canonical names so charts/UI re-use logic
        if "pv_w" in out: out["ppv"] = out["pv_w"]
        if "load_w" in out: out["consumptionPower"] = out["load_w"]
        # Grid: SolarEdge "GRID" is signed in flow direction; we can't easily
        # split into to/from without inspecting connections[]. Surface as-is.
        if "grid_w" in out: out["gridPower"] = out["grid_w"]
        # Storage signed: positive = charging?
        if "storage_w" in out:
            sw = out["storage_w"]
            if sw >= 0: out["pCharge"] = sw
            else: out["pDisCharge"] = -sw
        return out

    async def energy(self, serial: str) -> dict[str, Any]:
        """`overview.json` carries lifetime + today/month/year energy."""
        data = await self._get(f"/site/{self._se_site_id}/overview.json")
        ov = data.get("overview") or {}
        out: dict[str, Any] = {}
        for key, dst in (("lifeTimeData", "totalYielding"), ("lastYearData", "yearYielding"),
                         ("lastMonthData", "monthYielding"), ("lastDayData", "todayYielding")):
            blk = ov.get(key) or {}
            if isinstance(blk.get("energy"), (int, float)):
                out[dst] = float(blk["energy"])  # Wh
        if isinstance(ov.get("currentPower", {}).get("power"), (int, float)):
            out["currentPower"] = float(ov["currentPower"]["power"])
        return out

    async def battery(self, serial: str) -> dict[str, Any]:
        """SolarEdge battery details — limited compared to EG4."""
        data = await self._get(f"/site/{self._se_site_id}/currentPowerFlow.json")
        flow = data.get("siteCurrentPowerFlow") or {}
        storage = flow.get("STORAGE") or {}
        out: dict[str, Any] = {
            "totalVoltageText": "",
            "currentText": "",
            "battery_units": [],
        }
        if storage.get("chargeLevel") is not None:
            out["soc"] = float(storage["chargeLevel"])
        if storage.get("currentPower") is not None:
            out["currentPowerW"] = storage["currentPower"] * 1000
        return out

    async def fetch_day(self, serial, date_text, tz_offset_minutes):
        """15-minute resolution power across one local day."""
        start_dt = datetime.fromisoformat(date_text).replace(
            tzinfo=timezone(timedelta(minutes=tz_offset_minutes))
        )
        end_dt = start_dt + timedelta(days=1)
        params = {
            "timeUnit": "QUARTER_OF_AN_HOUR",
            "startTime": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "endTime": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        }
        data = await self._get(f"/site/{self._se_site_id}/powerDetails", params=params)
        meters = (data.get("powerDetails") or {}).get("meters") or []
        # Reduce to a merged ts -> {field: value} map
        merged: dict[int, dict[str, float]] = {}
        type_map = {
            "Production": "ppv",
            "Consumption": "consumptionPower",
            "SelfConsumption": "self_consumption",
            "FeedIn": "pToGrid",
            "Purchased": "pToUser",
        }
        for m in meters:
            field = type_map.get(m.get("type"), m.get("type"))
            for v in m.get("values") or []:
                if v.get("value") is None:
                    continue
                ts_local = datetime.strptime(v["date"], "%Y-%m-%d %H:%M:%S")
                ts_local = ts_local.replace(tzinfo=timezone(timedelta(minutes=tz_offset_minutes)))
                ts_ms = int(ts_local.astimezone(timezone.utc).timestamp() * 1000)
                merged.setdefault(ts_ms, {})[field] = float(v["value"])
        return sorted(merged.items())
