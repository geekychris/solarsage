"""Vendor adapter contract.

A SolarSage adapter wraps one vendor's monitoring portal. All adapters expose
the same surface so the rest of the app doesn't care whether data came from EG4,
SolarEdge, Q.Cells, or whatever ships next.

Methods that don't make sense for a vendor should raise NotImplementedError —
the caller will degrade gracefully (sync may skip a day, scheduler will use
clear-sky max only, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Inverter:
    serial: str
    plant_id: str | int | None
    plant_name: str | None
    model: str | None
    extra: dict[str, Any]


class SiteAdapter(ABC):
    vendor: str  # subclasses set this to "eg4" / "solaredge" / etc.

    def __init__(self, site_id: str, credentials: dict[str, Any], config: dict[str, Any]):
        self.site_id = site_id
        self.credentials = credentials
        self.config = config

    # Lifecycle -----------------------------------------------------------
    @abstractmethod
    async def login(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    # Discovery -----------------------------------------------------------
    @abstractmethod
    def list_inverters(self) -> list[Inverter]: ...

    # Live data (all return plain dicts of numeric fields) ----------------
    @abstractmethod
    async def runtime(self, serial: str) -> dict[str, Any]: ...

    @abstractmethod
    async def energy(self, serial: str) -> dict[str, Any]: ...

    @abstractmethod
    async def battery(self, serial: str) -> dict[str, Any]:
        """Returns rollup dict; may include "battery_units": [...]."""

    # Historical backfill -------------------------------------------------
    async def fetch_day(
        self, serial: str, date_text: str, tz_offset_minutes: int
    ) -> list[tuple[int, dict[str, float]]]:
        """Return [(ts_ms, {field: value}), ...] for the given local date.

        Default implementation: not supported. Override per vendor.
        """
        raise NotImplementedError(f"{self.vendor} adapter does not support historical backfill")
