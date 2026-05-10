"""Q.Cells adapter — stub.

Q.Cells makes panels; ESS / monitoring varies by region and hardware partner.
Common pairings:
  * Q.HOME ESS uses Hyundai/Q.Cells inverters with the Q.OMMAND portal
  * Q.Cells panels are frequently paired with Enphase microinverters,
    monitored via Enphase Enlighten (https://enlighten.enphaseenergy.com)
  * EU residential bundles sometimes use Sungrow / Solis inverters

Until we know which portal the user's site speaks to, this adapter accepts
credentials and config but refuses to run. Implementations to add when we
know:
  * Enphase Enlighten REST API — requires API key + system_id, supports
    /api/v4/systems/{id}/summary, telemetry/production, /telemetry/storage.
  * Q.OMMAND — undocumented; would need browser-traffic inspection.
"""

from __future__ import annotations

from typing import Any

from .base import Inverter, SiteAdapter


class QCellAdapter(SiteAdapter):
    vendor = "qcell"

    async def login(self) -> None:
        portal = self.config.get("portal", "unknown")
        raise NotImplementedError(
            f"Q.Cells adapter not yet implemented (portal hint: {portal!r}). "
            "Tell us which portal you log into — Q.OMMAND, Enphase Enlighten, "
            "Sungrow iSolarCloud, etc. — and we'll add the right backend."
        )

    async def close(self) -> None: pass
    def list_inverters(self) -> list[Inverter]: return []
    async def runtime(self, serial): return {}
    async def energy(self, serial): return {}
    async def battery(self, serial): return {"battery_units": []}
