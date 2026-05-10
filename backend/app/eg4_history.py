"""Extension of EG4InverterAPI to call the (undocumented) chart endpoints.

The base library only exposes live-snapshot endpoints. The portal also has
analytics endpoints that power the day/week/month charts in the web UI; these
are what we use to backfill historical data into our SQLite store.

Endpoint paths confirmed from `joyfulhouse/pylxpweb` and `matt-dreyer/eg4_python`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from eg4_inverter_api import EG4InverterAPI
from eg4_inverter_api.exceptions import EG4APIError

DAY_MULTI_LINE_PARALLEL = "/WManage/api/analyze/chart/dayMultiLineParallel"
DAY_LINE = "/WManage/api/analyze/chart/dayLine"
ENERGY_MONTH_COLUMN = "/WManage/api/analyze/energy/monthColumn"

log = logging.getLogger("eg4.history")

# Map chart-endpoint field names → the names we use in the SQLite samples table
# so live polling and historical backfill produce a unified time-series.
CHART_FIELD_MAP = {
    "solarPv": "ppv",
    "consumption": "consumptionPower",
    "batteryDischarging": "pDisCharge",
    "batteryCharging": "pCharge",
    "gridPower": "gridPower",
    "acCouplePower": "acCouplePower",
    "soc": "soc",
}


@dataclass
class HistoricalSample:
    ts_ms: int
    fields: dict[str, float]


def _parse_point_ts(point: dict[str, Any], tz_offset_minutes: int) -> int | None:
    """The chart endpoint returns a local wall-clock date. We need UTC ms."""
    try:
        y, mo, d = int(point["year"]), int(point["month"]), int(point["day"])
        h, mi, s = int(point.get("hour", 0)), int(point.get("minute", 0)), int(point.get("second", 0))
        local_dt = datetime(y, mo, d, h, mi, s, tzinfo=timezone(timedelta(minutes=tz_offset_minutes)))
        return int(local_dt.astimezone(timezone.utc).timestamp() * 1000)
    except (KeyError, ValueError, TypeError):
        return None


class EG4ChartError(EG4APIError):
    """Carries HTTP + body context so the caller can surface it in /api/sync."""
    def __init__(self, path: str, status: int, body_sample: str, content_type: str = ""):
        super().__init__(f"{path} -> HTTP {status}; body[:200]={body_sample[:200]!r}")
        self.path = path
        self.status = status
        self.body_sample = body_sample[:1024]
        self.content_type = content_type


async def _post(api: EG4InverterAPI, path: str, payload: str) -> dict[str, Any]:
    """POST with the authenticated session, transparent re-auth on 401."""
    session = await api._get_session()
    url = f"{api._base_url}{path}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
    }

    async def do(s):
        async with s.post(url, data=payload, headers=headers) as r:
            text = await r.text()
            return r.status, r.headers.get("Content-Type", ""), text

    status, ct, text = await do(session)
    if status == 401:
        await api.login(ignore_ssl=api._ignore_ssl)
        session = await api._get_session()
        status, ct, text = await do(session)

    if status != 200:
        raise EG4ChartError(path, status, text, ct)
    # The portal sometimes returns HTML (login redirect) with a 200 status
    # when the session is bad. Guard against that.
    if "application/json" not in ct and not text.strip().startswith("{"):
        raise EG4ChartError(path, status, text, ct)
    import json as _json
    try:
        return _json.loads(text)
    except _json.JSONDecodeError as exc:
        raise EG4ChartError(path, status, text, ct) from exc


def _parse_time_string(time_str: str, tz_offset_minutes: int) -> int | None:
    """Parse 'YYYY-MM-DD HH:MM:SS' (the chart endpoint's `time` field).

    Use this in preference to the point's year/month/day fields — those are
    Java-style 0-indexed for month (May = 4), which silently produces a
    one-month-off timestamp.
    """
    try:
        from datetime import datetime as _dt
        dt = _dt.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        local = dt.replace(tzinfo=timezone(timedelta(minutes=tz_offset_minutes)))
        return int(local.astimezone(timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


# Chart attrs that we want to backfill, in firmware-native names. The sync
# endpoint loops over these per day. `ppv` total is synthesized from ppv1..ppv3
# because that attribute isn't chartable on the SNA-US firmware.
CHART_ATTRS = (
    "ppv1", "ppv2", "ppv3", "ppv4",
    "pCharge", "pDisCharge",
    "pToGrid", "pToUser",
    "peps", "pEpsL1N", "pEpsL2N",
    "soc", "vBat", "bmsBatCurrent",
    "vacr", "vacs", "vact", "fac",
    "vpv1", "vpv2", "vpv3",
    "tBat", "tinner", "tradiator1", "tradiator2",
    "feps", "vepsr", "vepss", "vepst",
    "acCouplePower",
    "status",
)


async def fetch_day_lines(
    api: EG4InverterAPI,
    serial: str,
    date_text: str,
    tz_offset_minutes: int,
    attrs: tuple[str, ...] = CHART_ATTRS,
    concurrency: int = 4,
) -> list[HistoricalSample]:
    """Fetch one local day of historical data via per-attribute dayLine calls.

    `dayMultiLineParallel` returns empty `data: []` on SNA-US firmware. Instead
    we issue one POST per attribute (in parallel, bounded by `concurrency`)
    and merge points across attrs by timestamp.
    """
    import asyncio

    sem = asyncio.Semaphore(concurrency)
    results: dict[str, list[dict[str, Any]]] = {}

    async def fetch_one(attr: str) -> tuple[str, list[dict[str, Any]]]:
        payload = f"serialNum={serial}&attr={attr}&dateText={date_text}"
        async with sem:
            body = await _post(api, DAY_LINE, payload)
        if not body.get("success"):
            return attr, []
        return attr, body.get("data") or []

    coros = [fetch_one(a) for a in attrs]
    for fut in asyncio.as_completed(coros):
        attr, points = await fut
        results[attr] = points

    # Merge: bucket points by timestamp across attrs
    merged: dict[int, dict[str, float]] = {}
    for attr, points in results.items():
        for p in points:
            v = p.get("value")
            if not isinstance(v, (int, float)):
                continue
            ts = _parse_time_string(p.get("time", ""), tz_offset_minutes)
            if ts is None:
                continue
            merged.setdefault(ts, {})[attr] = float(v)

    # Synthesize total PV from per-string powers when we don't already have it
    for ts, fields in merged.items():
        if "ppv" not in fields:
            strings = [fields.get(s, 0.0) for s in ("ppv1", "ppv2", "ppv3", "ppv4")]
            if any(s != 0 for s in strings):
                fields["ppv"] = sum(strings)
        # Synthesize total EPS load = pEpsL1N + pEpsL2N (firmware sometimes
        # zeroes consumptionPower because everything's on EPS)
        if "consumptionPower" not in fields and (
            "pEpsL1N" in fields or "pEpsL2N" in fields
        ):
            fields["consumptionPower"] = fields.get("pEpsL1N", 0.0) + fields.get("pEpsL2N", 0.0)

    return [
        HistoricalSample(ts_ms=ts, fields=fields)
        for ts, fields in sorted(merged.items())
    ]


# Back-compat alias — the sync endpoint imports this name and we keep the
# semantics ("fetch one local day, return HistoricalSamples"), just on the
# endpoint that actually works for this firmware.
fetch_day_multiline = fetch_day_lines


async def fetch_day_attr(
    api: EG4InverterAPI, serial: str, date_text: str, attr: str, tz_offset_minutes: int
) -> list[tuple[int, float]]:
    """Hi-res per-attribute time series for one day. Use for drill-down."""
    payload = f"serialNum={serial}&attr={attr}&dateText={date_text}"
    body = await _post(api, DAY_LINE, payload)
    if not body.get("success"):
        raise EG4APIError(f"dayLine({attr}) failed: {body}")
    out: list[tuple[int, float]] = []
    # dayLine packs time and value separately; format varies. Handle both shapes.
    for point in body.get("dataPoints", []) or body.get("data", []) or []:
        t = point.get("time") or point.get("timeText")
        v = point.get("value")
        if t is None or v is None:
            continue
        try:
            # "HH:MM" or "HH:MM:SS"
            parts = t.split(":")
            h = int(parts[0]); m = int(parts[1]); s = int(parts[2]) if len(parts) > 2 else 0
            y, mo, d = map(int, date_text.split("-"))
            ldt = datetime(y, mo, d, h, m, s, tzinfo=timezone(timedelta(minutes=tz_offset_minutes)))
            ts = int(ldt.astimezone(timezone.utc).timestamp() * 1000)
            out.append((ts, float(v)))
        except (ValueError, IndexError):
            continue
    return out
