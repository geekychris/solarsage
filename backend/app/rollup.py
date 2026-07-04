"""Daily long-term-retention rollup to Google Sheets.

Runs a check every 15 min. Whenever the local wall clock is past
00:30 AND the "Daily Stats" tab is missing yesterday's row, it
appends yesterday's stats to two tabs:

  * "Daily Stats"   — one row per day (dedup on ``date`` col)
      date, net_uptime_pct, net_outages, net_longest_outage_min,
      water_gallons, power_max_w, power_avg_w, solar_kwh,
      consumption_kwh, min_soc, max_soc

  * "Temp Snapshots" — one row per (date × hour × sensor)
      date, hour, sensor, temperature, unit

Idempotent: on startup + each tick, checks the sheet's ``date``
column (Daily Stats) and ``date`` column (Temp Snapshots) to skip
days already written. Backfills up to ``ROLLUP_BACKFILL_DAYS`` past
days it has data for.

Data sources
------------
* Network uptime / outages / longest gap  → SQLite ``network_checks``
  + ``network_outages``.
* Power (max, avg) + solar/consumption kWh + SoC (min, max)
  → SQLite ``samples`` (avg-W over the day × 24 / 1000 for kWh).
* Water gallons → HA totalizer entity read from the ``dab_pump_history``
  widget's config (falls back to widget default).
* House / patio temperatures → HA sensors read from the
  ``climate_chart`` widget config (which itself falls back to
  ``solar_vitals.room_sensors`` — one place to configure).

Env-tunable
-----------
  SOLARSAGE_ROLLUP_HOURS=6,12,18,22   snapshot hours (local)
  SOLARSAGE_ROLLUP_TZ=America/Tijuana override tz (else DB settings)
  ROLLUP_BACKFILL_DAYS=7              days to backfill on startup
  ROLLUP_DISABLED=1                   turn off the whole task
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

import aiohttp
import aiosqlite

from .sheets import SheetsSync
from .storage import History
from .widgets.store import WidgetStore

log = logging.getLogger("solarsage.rollup")


DAILY_TAB = "Daily Stats"
DAILY_COLS = [
    "date",
    "net_uptime_pct",
    "net_outages",
    "net_longest_outage_min",
    "water_gallons",
    "power_max_w",
    "power_avg_w",
    "solar_kwh",
    "consumption_kwh",
    "min_soc",
    "max_soc",
]

TEMPS_TAB = "Temp Snapshots"
TEMPS_COLS = ["date", "hour", "sensor", "temperature", "unit"]

DEFAULT_SNAPSHOT_HOURS = [6, 12, 18, 22]
DEFAULT_BACKFILL_DAYS = 7
TICK_SECONDS = 15 * 60


# ---------- config helpers -----------------------------------------------

def _snapshot_hours() -> list[int]:
    raw = os.getenv("SOLARSAGE_ROLLUP_HOURS")
    if not raw:
        return DEFAULT_SNAPSHOT_HOURS
    try:
        hours = sorted({int(h.strip()) for h in raw.split(",") if h.strip()})
        return [h for h in hours if 0 <= h <= 23] or DEFAULT_SNAPSHOT_HOURS
    except ValueError:
        return DEFAULT_SNAPSHOT_HOURS


def _tz_offset_minutes_for(tz_name: str) -> int:
    try:
        from zoneinfo import ZoneInfo
        return int(datetime.now(ZoneInfo(tz_name)).utcoffset().total_seconds() / 60)
    except Exception:
        return -420  # PDT fallback


async def _resolve_tz_offset_min(history: History) -> tuple[str, int]:
    tz_env = os.getenv("SOLARSAGE_ROLLUP_TZ")
    if tz_env:
        return tz_env, _tz_offset_minutes_for(tz_env)
    raw = await history.get_settings()
    tz_val = raw.get("tz")
    if tz_val:
        # settings are JSON-encoded strings
        import json
        try:
            tz_val = json.loads(tz_val)
        except Exception:  # noqa: BLE001
            pass
    tz_name = str(tz_val or "America/Tijuana")
    return tz_name, _tz_offset_minutes_for(tz_name)


def _day_bounds_utc_ms(day: date, tz_offset_min: int) -> tuple[int, int]:
    tz = timezone(timedelta(minutes=tz_offset_min))
    start = datetime.combine(day, dtime.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return (
        int(start.astimezone(timezone.utc).timestamp() * 1000),
        int(end.astimezone(timezone.utc).timestamp() * 1000),
    )


async def _serials(history: History) -> list[str]:
    async with aiosqlite.connect(history.db_path) as db:
        cur = await db.execute(
            "SELECT DISTINCT serial_num FROM samples LIMIT 10",
        )
        return [r[0] for r in await cur.fetchall()]


# ---------- HA history helpers -------------------------------------------

async def _ha_history(
    http: aiohttp.ClientSession, ha_url: str, ha_token: str,
    entity_id: str, start_iso: str, end_iso: str,
    *, no_attributes: bool = False,
) -> list[dict]:
    params = {
        "filter_entity_id": entity_id,
        "end_time": end_iso,
        "minimal_response": "true",
    }
    if no_attributes:
        params["no_attributes"] = "true"
    try:
        async with http.get(
            f"{ha_url}/api/history/period/{start_iso}",
            params=params,
            headers={"Authorization": f"Bearer {ha_token}"},
            timeout=30,
        ) as r:
            if r.status != 200:
                log.warning("HA history %s → HTTP %s", entity_id, r.status)
                return []
            payload = await r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("HA history %s failed: %s", entity_id, exc)
        return []
    if not payload or not isinstance(payload, list) or not payload[0]:
        return []
    return payload[0]


def _row_ts_ms(row: dict) -> int | None:
    lc = row.get("last_changed") or row.get("last_updated")
    if not lc:
        return None
    try:
        dt = datetime.fromisoformat(str(lc).replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def _last_state_at_or_before(
    rows: list[dict], target_ms: int,
) -> tuple[float | None, str]:
    """Return (numeric_state, unit) of the last row with ts <= target_ms.
    Skips unavailable/unknown/blank states."""
    best = None
    for h in rows:
        state = h.get("state")
        if state in (None, "unavailable", "unknown", ""):
            continue
        ts = _row_ts_ms(h)
        if ts is None:
            continue
        if ts > target_ms:
            break
        best = h
    if not best:
        return None, ""
    try:
        v = float(best["state"])
    except (TypeError, ValueError):
        return None, ""
    attrs = best.get("attributes") or {}
    unit = attrs.get("unit_of_measurement") or ""
    return v, unit


# ---------- per-day computations -----------------------------------------

async def _compute_daily_row(
    history: History, http: aiohttp.ClientSession | None,
    day: date, tz_offset_min: int,
    serial: str | None,
    ha_url: str, ha_token: str,
    dab_totalizer_eid: str,
) -> dict[str, Any]:
    start_ms, end_ms = _day_bounds_utc_ms(day, tz_offset_min)
    row: dict[str, Any] = {"date": day.isoformat()}

    # --- network uptime
    summary = await history.network_summary(start_ms, end_ms)
    total = summary.get("total") or 0
    ok = summary.get("ok_count") or 0
    row["net_uptime_pct"] = round(100.0 * ok / total, 2) if total else ""

    outages = await history.network_outages_in_range(start_ms, end_ms)
    row["net_outages"] = len(outages)
    longest_min = 0.0
    for o in outages:
        s = max(o["started_ts"], start_ms)
        e = min(o["ended_ts"] or end_ms, end_ms)
        gap = max(0, e - s) / 60_000
        if gap > longest_min:
            longest_min = gap
    row["net_longest_outage_min"] = round(longest_min, 1) if outages else 0

    # --- power / solar / SoC (needs a serial)
    if serial:
        async def _kwh_from_avg_w(field: str) -> float | str:
            stats = await history.overall_stats(serial, field, start_ms, end_ms)
            if stats["avg"] is None:
                return ""
            return round(stats["avg"] * 24 / 1000, 2)

        cons_stats = await history.overall_stats(
            serial, "consumptionPower", start_ms, end_ms,
        )
        row["power_max_w"] = (
            round(cons_stats["max"], 0) if cons_stats["max"] is not None else ""
        )
        row["power_avg_w"] = (
            round(cons_stats["avg"], 0) if cons_stats["avg"] is not None else ""
        )
        row["solar_kwh"] = await _kwh_from_avg_w("ppv")
        row["consumption_kwh"] = await _kwh_from_avg_w("consumptionPower")
        soc_stats = await history.overall_stats(serial, "soc", start_ms, end_ms)
        row["min_soc"] = (
            round(soc_stats["min"], 0) if soc_stats["min"] is not None else ""
        )
        row["max_soc"] = (
            round(soc_stats["max"], 0) if soc_stats["max"] is not None else ""
        )
    else:
        for k in ("power_max_w", "power_avg_w", "solar_kwh",
                  "consumption_kwh", "min_soc", "max_soc"):
            row[k] = ""

    # --- water gallons (HA totalizer delta over the day)
    row["water_gallons"] = ""
    if http and ha_url and ha_token and dab_totalizer_eid:
        # Fetch from (start - 6h) to (end + 5m) so we're sure to have
        # a "last state before start" reading and a "last state before end".
        pad_start = start_ms - 6 * 3_600_000
        pad_end = end_ms + 5 * 60_000
        start_iso = datetime.fromtimestamp(pad_start / 1000, tz=timezone.utc).isoformat()
        end_iso = datetime.fromtimestamp(pad_end / 1000, tz=timezone.utc).isoformat()
        rows = await _ha_history(
            http, ha_url, ha_token, dab_totalizer_eid, start_iso, end_iso,
            no_attributes=True,
        )
        v_start, _ = _last_state_at_or_before(rows, start_ms)
        v_end, _ = _last_state_at_or_before(rows, end_ms - 1)
        if v_start is not None and v_end is not None and v_end >= v_start:
            row["water_gallons"] = round(v_end - v_start, 1)

    return row


async def _compute_temp_rows(
    http: aiohttp.ClientSession,
    day: date, tz_offset_min: int,
    ha_url: str, ha_token: str,
    sensors: list[dict[str, Any]],
    hours: list[int],
) -> list[dict[str, Any]]:
    if not sensors or not hours:
        return []
    tz = timezone(timedelta(minutes=tz_offset_min))
    day_start = datetime.combine(day, dtime.min, tzinfo=tz)
    out: list[dict[str, Any]] = []
    for sensor in sensors:
        eid = sensor.get("temp_entity")
        if not eid:
            continue
        name = sensor.get("name") or eid
        # Fetch the whole day (plus 1h lead-in so pre-06:00 has a value).
        pad_start = day_start - timedelta(hours=1)
        pad_end = day_start + timedelta(days=1, minutes=5)
        rows = await _ha_history(
            http, ha_url, ha_token, eid,
            pad_start.astimezone(timezone.utc).isoformat(),
            pad_end.astimezone(timezone.utc).isoformat(),
            no_attributes=False,
        )
        for h in hours:
            target = day_start + timedelta(hours=h)
            target_ms = int(target.timestamp() * 1000)
            value, unit = _last_state_at_or_before(rows, target_ms)
            if value is None:
                continue
            out.append({
                "date": day.isoformat(),
                "hour": f"{h:02d}:00",
                "sensor": name,
                "temperature": round(value, 2),
                "unit": unit,
            })
    return out


# ---------- widget-config loaders ----------------------------------------

async def _get_dab_totalizer(db_path: str) -> str:
    store = WidgetStore(db_path)
    cfg = await store.get_config("dab_pump_history") or {}
    return (cfg.get("totalizer_eid") or "").strip()


async def _get_climate_sensors(db_path: str) -> list[dict[str, Any]]:
    store = WidgetStore(db_path)
    cfg = await store.get_config("climate_chart") or {}
    sensors = cfg.get("sensors")
    if not sensors:
        sv = await store.get_config("solar_vitals") or {}
        sensors = sv.get("room_sensors") or []
    return [s for s in sensors if s.get("temp_entity")]


# ---------- driver -------------------------------------------------------

async def _existing_daily_dates(sheets: SheetsSync) -> set[str]:
    try:
        return set(await sheets.list_column(DAILY_TAB, "date"))
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s dates: %s", DAILY_TAB, exc)
        return set()


async def _existing_temp_keys(sheets: SheetsSync) -> set[tuple[str, str, str]]:
    """Existing (date, hour, sensor) tuples in the Temp Snapshots tab."""
    try:
        rows = await sheets.read(TEMPS_TAB, TEMPS_COLS)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read %s: %s", TEMPS_TAB, exc)
        return set()
    return {(r.get("date", ""), r.get("hour", ""), r.get("sensor", ""))
            for r in rows}


async def run_rollup_for_day(
    history: History, sheets: SheetsSync, db_path: str, day: date,
    *, skip_if_exists: bool = True,
) -> dict[str, Any]:
    """Compute + append the rollup rows for one specific local day."""
    tz_name, tz_off = await _resolve_tz_offset_min(history)
    serials = await _serials(history)
    serial = serials[0] if serials else None

    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN") or ""
    dab_eid = await _get_dab_totalizer(db_path)
    sensors = await _get_climate_sensors(db_path)
    hours = _snapshot_hours()

    result = {
        "date": day.isoformat(), "tz": tz_name,
        "daily_written": False, "temps_written": 0, "skipped": [],
    }

    await sheets.ensure_tab(DAILY_TAB, DAILY_COLS)
    await sheets.ensure_tab(TEMPS_TAB, TEMPS_COLS)

    existing_dates = await _existing_daily_dates(sheets)
    async with aiohttp.ClientSession() as http:
        # --- daily row
        if skip_if_exists and day.isoformat() in existing_dates:
            result["skipped"].append("daily (already present)")
        else:
            daily_row = await _compute_daily_row(
                history, http, day, tz_off, serial,
                ha_url, ha_token, dab_eid,
            )
            await sheets.append_rows(DAILY_TAB, DAILY_COLS, [daily_row])
            result["daily_written"] = True
            result["daily_row"] = daily_row

        # --- temp snapshots
        if not (ha_url and ha_token and sensors):
            result["skipped"].append("temps (HA/sensors not configured)")
        else:
            existing_keys = (
                await _existing_temp_keys(sheets) if skip_if_exists else set()
            )
            all_rows = await _compute_temp_rows(
                http, day, tz_off, ha_url, ha_token, sensors, hours,
            )
            fresh = [
                r for r in all_rows
                if (r["date"], r["hour"], r["sensor"]) not in existing_keys
            ]
            if fresh:
                await sheets.append_rows(TEMPS_TAB, TEMPS_COLS, fresh)
            result["temps_written"] = len(fresh)

    return result


async def _backfill(
    history: History, sheets: SheetsSync, db_path: str,
    tz_offset_min: int, max_days: int,
) -> None:
    """On startup, add any missing yesterday...N-days-back rows."""
    now_local = datetime.now(timezone(timedelta(minutes=tz_offset_min)))
    yesterday = now_local.date() - timedelta(days=1)
    for i in range(max_days):
        day = yesterday - timedelta(days=i)
        try:
            r = await run_rollup_for_day(
                history, sheets, db_path, day, skip_if_exists=True,
            )
            if r["daily_written"] or r["temps_written"]:
                log.info(
                    "rollup backfill %s: daily=%s temps=%d",
                    day, r["daily_written"], r["temps_written"],
                )
        except Exception:
            log.exception("rollup backfill day %s failed", day)


async def run_rollup(
    history: History, sheets: SheetsSync | None, db_path: str,
) -> None:
    if os.getenv("ROLLUP_DISABLED") == "1":
        log.info("rollup disabled by ROLLUP_DISABLED=1")
        return
    if sheets is None:
        log.info("rollup skipped — Google Sheets not configured")
        return
    backfill_days = int(os.getenv("ROLLUP_BACKFILL_DAYS", str(DEFAULT_BACKFILL_DAYS)))
    tz_name, tz_off = await _resolve_tz_offset_min(history)
    log.info(
        "rollup task started (tz=%s, snapshot_hours=%s, backfill=%d days)",
        tz_name, _snapshot_hours(), backfill_days,
    )

    try:
        await _backfill(history, sheets, db_path, tz_off, backfill_days)
    except Exception:
        log.exception("rollup startup backfill failed")

    while True:
        try:
            tz_name, tz_off = await _resolve_tz_offset_min(history)
            now_local = datetime.now(timezone(timedelta(minutes=tz_off)))
            # Only run yesterday's rollup after 00:30 local — leaves a
            # buffer for the last widget refreshes / late samples.
            if now_local.hour == 0 and now_local.minute < 30:
                pass
            else:
                yesterday = now_local.date() - timedelta(days=1)
                r = await run_rollup_for_day(
                    history, sheets, db_path, yesterday, skip_if_exists=True,
                )
                if r["daily_written"] or r["temps_written"]:
                    log.info(
                        "rollup wrote %s: daily=%s temps=%d",
                        yesterday, r["daily_written"], r["temps_written"],
                    )
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("rollup tick failed")

        try:
            await asyncio.sleep(TICK_SECONDS)
        except asyncio.CancelledError:
            return
