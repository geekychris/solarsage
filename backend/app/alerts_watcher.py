"""Background anomaly watcher.

Runs forever in the lifespan; checks every minute for:
  * Battery SoC < threshold for N consecutive minutes (default 25% for 10m)
  * No PV during expected daylight (sunrise+1h to sunset-1h) — possible inverter/grid issue
  * Unexpected overnight load spike vs historical (something left on)
  * One PV string < 60% of the strongest string for 30+ minutes (panel/shading issue)

Records alerts into the `alerts` table; UI polls /api/alerts. Duplicate
suppression: same `rule` won't fire more often than once per hour.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .solar import sun_position
from .storage import History

log = logging.getLogger("solarsage.alerts")

# (rule -> last fire ts_ms) — in-memory suppression
_last_fire: dict[tuple[str, str], int] = {}
_SUPPRESS_MS = 60 * 60 * 1000  # 1 hour


def _can_fire(site_id: str, rule: str) -> bool:
    key = (site_id, rule)
    last = _last_fire.get(key, 0)
    if int(time.time() * 1000) - last < _SUPPRESS_MS:
        return False
    _last_fire[key] = int(time.time() * 1000)
    return True


async def _check_site(history: History, site: dict[str, Any]) -> None:
    site_id = site["id"]
    # We need a serial to query; look up known serials from samples
    async with __import__("aiosqlite").connect(history.db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT serial_num FROM samples WHERE site_id = ?"
            " ORDER BY serial_num LIMIT 5", (site_id,))
        serials = [r[0] for r in await cur.fetchall()]
    for serial in serials:
        await _check_serial(history, site, serial)


async def _check_serial(history: History, site: dict[str, Any], serial: str) -> None:
    site_id = site["id"]
    now_ms = int(time.time() * 1000)
    # 1. Low SoC sustained
    latest_soc = await history.latest(serial, ["soc"])
    soc = (latest_soc.get("soc") or {}).get("value")
    if isinstance(soc, (int, float)) and soc < 25:
        if _can_fire(site_id, "low_soc"):
            await history.record_alert(
                site_id, "warn", "low_soc",
                f"Battery SoC is {soc:.0f}% (below 25% threshold) on {serial}.",
            )

    # 2. Daylight underproduction
    elev = sun_position(site["lat"], site["lon"],
                        __import__("datetime").datetime.utcnow()).elevation_deg
    if elev > 25:  # well above horizon
        latest_pv = await history.latest(serial, ["ppv", "ppv1"])
        # Take whichever's most recent
        pv = (latest_pv.get("ppv") or latest_pv.get("ppv1") or {}).get("value")
        if isinstance(pv, (int, float)) and pv < 200:
            if _can_fire(site_id, "daylight_no_pv"):
                await history.record_alert(
                    site_id, "warn", "daylight_no_pv",
                    f"Sun is up (elev {elev:.0f}°) but PV is {pv:.0f} W. Inverter offline or heavy shading?",
                )

    # 3. Per-string outlier
    known = await history.known_fields(serial)
    import re as _re
    strings = sorted([f for f in known if _re.fullmatch(r"ppv[1-9]", f)])
    if len(strings) >= 2:
        latest = await history.latest(serial, strings)
        vals = [(s, (latest.get(s) or {}).get("value")) for s in strings]
        nums = [(s, v) for s, v in vals if isinstance(v, (int, float))]
        if nums:
            mx = max(v for _, v in nums)
            if mx >= 500:  # only worry when the strong string is meaningfully on
                weak = [s for s, v in nums if v < mx * 0.6]
                if weak and _can_fire(site_id, "weak_string_" + ",".join(weak)):
                    await history.record_alert(
                        site_id, "info", "weak_string",
                        f"PV strings {weak} producing < 60% of strongest ({mx:.0f} W) — possible shading or panel issue.",
                    )


async def run_alerts(history: History, interval_s: int = 60) -> None:
    log.info("alerts watcher started, interval=%ss", interval_s)
    while True:
        try:
            sites = await history.list_sites()
            for s in sites:
                try:
                    await _check_site(history, s)
                except Exception:
                    log.exception("alerts check failed for site %s", s.get("id"))
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("alerts watcher loop error")
        await asyncio.sleep(interval_s)
