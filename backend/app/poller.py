"""Background poller that snapshots all inverters on a session into SQLite."""

from __future__ import annotations

import asyncio
import logging

from eg4_inverter_api.exceptions import EG4APIError, EG4AuthError

from .session_store import Session
from .storage import History

log = logging.getLogger("eg4.poller")


async def _snapshot_inverter(session: Session, history: History, serial_num: str) -> None:
    client = session.client
    async with session.lock:
        client.set_selected_inverter(serialNum=serial_num)
        runtime = await client.get_inverter_runtime_async()
        energy = await client.get_inverter_energy_async()
        battery = await client.get_inverter_battery_async()

    if hasattr(runtime, "to_dict"):
        await history.record(serial_num, "runtime", runtime.to_dict())
    if hasattr(energy, "to_dict"):
        await history.record(serial_num, "energy", energy.to_dict())
    if hasattr(battery, "to_dict"):
        bdict = battery.to_dict()
        # battery_units is a list — flatten the rollup fields and skip the list
        rollup = {k: v for k, v in bdict.items() if k != "battery_units"}
        await history.record(serial_num, "battery", rollup)
        # also store per-unit SoC/voltage/current
        for unit in bdict.get("battery_units", []):
            idx = unit.get("batIndex")
            if idx is None:
                continue
            per_unit = {
                f"unit{idx}_soc": unit.get("soc"),
                f"unit{idx}_soh": unit.get("soh"),
                f"unit{idx}_voltage": unit.get("totalVoltage"),
                f"unit{idx}_current": unit.get("current"),
                f"unit{idx}_cycles": unit.get("cycleCnt"),
            }
            # filter Nones — record() ignores non-numerics anyway
            await history.record(serial_num, "battery_unit", per_unit)


async def run_poller(session: Session, history: History, interval: int) -> None:
    """Forever-loop: snapshot every inverter on the account, sleep, repeat."""
    log.info("poller started for %s every %ss", session.username, interval)
    while True:
        try:
            inverters = session.client.get_inverters()
            for inv in inverters:
                try:
                    await _snapshot_inverter(session, history, inv.serialNum)
                except (EG4APIError, EG4AuthError) as exc:
                    log.warning("snapshot failed for %s: %s", inv.serialNum, exc)
                except Exception:
                    log.exception("unexpected error snapshotting %s", inv.serialNum)
        except asyncio.CancelledError:
            log.info("poller cancelled")
            raise
        except Exception:
            log.exception("poller loop error")
        await asyncio.sleep(interval)
