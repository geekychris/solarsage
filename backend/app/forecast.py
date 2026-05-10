"""Forecasts derived from stored EG4 history + a clear-sky envelope.

Two functions to know about:

- `solar_today(...)`     produces today's per-bucket curves: actual so far,
                        historical avg at this time-of-year-window, clearsky
                        envelope, and a forward-projected "expected" curve.
- `battery_completion(...)` integrates expected net charging power forward
                        from the current SoC to predict when the pack hits
                        100%, returning the projected SoC trajectory.

The historical curve is a simple bucketed average of the last N days, which
naturally gets better as more data accumulates. We don't filter by weather
because the EG4 portal doesn't expose any weather signal; over a couple weeks
the average smooths cloudy/clear days into a usable expectation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .solar import clearsky_power_w
from .storage import History

BUCKET_MIN = 15
BUCKETS_PER_DAY = 24 * 60 // BUCKET_MIN  # 96


@dataclass
class LocationConfig:
    lat: float
    lon: float
    tz_offset_minutes: int  # local minus UTC, e.g. PDT = -420
    peak_kw: float
    battery_capacity_kwh: float
    max_charge_kw: float  # inverter max charge rate (W cap on net battery in)


def _now_local(tz_offset_minutes: int) -> datetime:
    return datetime.now(timezone.utc).astimezone(
        timezone(timedelta(minutes=tz_offset_minutes))
    )


def _bucket_of(dt_local: datetime) -> int:
    return ((dt_local.hour * 60 + dt_local.minute) // BUCKET_MIN) * BUCKET_MIN


def _bucket_to_dt(bucket_minute: int, anchor_local: datetime) -> datetime:
    midnight = anchor_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(minutes=bucket_minute)


# Fields that might represent total instantaneous PV power. We pick whichever
# the EG4 firmware actually returns (it varies by model).
PV_FIELD_CANDIDATES = ("ppv", "ppvpCharge", "pPV", "totalPv", "ppv1", "totalPVPower")
LOAD_FIELD_CANDIDATES = ("consumptionPower", "pLoad", "totalLoad")
SOC_FIELD_CANDIDATES = (
    "unit0_soc",
    "unit1_soc",
    "soc",
    "batterySoc",
    "totalSoc",
)


async def pick_field(history: History, serial: str, candidates) -> Optional[str]:
    known = await history.known_fields(serial)
    for f in candidates:
        if f in known:
            return f
    return None


async def soc_now(history: History, serial: str) -> Optional[float]:
    """Average SoC across all per-unit fields we've recorded."""
    known = await history.known_fields(serial)
    unit_fields = sorted(f for f in known if f.endswith("_soc"))
    if not unit_fields:
        # try aggregate fields too
        for f in ("soc", "batterySoc", "totalSoc"):
            if f in known:
                unit_fields = [f]
                break
    if not unit_fields:
        return None
    latest = await history.latest(serial, unit_fields)
    values = [v["value"] for v in latest.values() if v.get("value") is not None]
    return sum(values) / len(values) if values else None


async def soc_rate_per_min(history: History, serial: str, window_min: int = 30) -> Optional[float]:
    """% SoC change per minute over the last `window_min`, averaged across units."""
    known = await history.known_fields(serial)
    unit_fields = sorted(f for f in known if f.endswith("_soc")) or [
        f for f in ("soc", "batterySoc", "totalSoc") if f in known
    ]
    if not unit_fields:
        return None
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    rates: list[float] = []
    for f in unit_fields:
        pts = await history.query(serial, f, now_ms - window_min * 60_000, now_ms, max_points=200)
        if len(pts) < 2:
            continue
        dt_min = (pts[-1]["ts"] - pts[0]["ts"]) / 60_000
        if dt_min <= 0:
            continue
        rates.append((pts[-1]["value"] - pts[0]["value"]) / dt_min)
    if not rates:
        return None
    return sum(rates) / len(rates)


async def historical_curve(
    history: History, serial: str, field: str, loc: LocationConfig, days: int = 7
) -> dict[int, float]:
    return await history.bucket_avg_by_time_of_day(
        serial,
        field,
        days=days,
        bucket_minutes=BUCKET_MIN,
        tz_offset_minutes=loc.tz_offset_minutes,
    )


async def solar_today(
    history: History, serial: str, loc: LocationConfig, hist_days: int = 7
) -> dict:
    pv_field = await pick_field(history, serial, PV_FIELD_CANDIDATES)
    load_field = await pick_field(history, serial, LOAD_FIELD_CANDIDATES)

    hist_pv = (
        await historical_curve(history, serial, pv_field, loc, hist_days) if pv_field else {}
    )
    hist_load = (
        await historical_curve(history, serial, load_field, loc, hist_days)
        if load_field
        else {}
    )

    now_local = _now_local(loc.tz_offset_minutes)
    now_bucket = _bucket_of(now_local)

    today_pv: dict[int, float] = {}
    if pv_field:
        # bucket-of-day for the last 24h, then filter to today only
        # (bucket_avg over last day naturally returns "today + last night")
        recent = await history.bucket_avg_by_time_of_day(
            serial, pv_field, days=1, bucket_minutes=BUCKET_MIN,
            tz_offset_minutes=loc.tz_offset_minutes,
        )
        # only keep buckets up to now
        today_pv = {b: v for b, v in recent.items() if b <= now_bucket}

    buckets = []
    for b in range(0, 24 * 60, BUCKET_MIN):
        bucket_dt_local = _bucket_to_dt(b, now_local)
        clearsky = clearsky_power_w(loc.lat, loc.lon, bucket_dt_local, loc.peak_kw)
        row = {
            "minute_of_day": b,
            "clearsky_w": clearsky,
            "historical_avg_w": hist_pv.get(b),
            "actual_w": today_pv.get(b) if b <= now_bucket else None,
            "historical_load_w": hist_load.get(b),
        }
        buckets.append(row)

    days_of_history = 0
    if pv_field:
        first = await history.first_sample_ts(serial, pv_field)
        if first is not None:
            days_of_history = max(
                1, int((datetime.now(timezone.utc).timestamp() * 1000 - first) / 86_400_000)
            )

    return {
        "tz_offset_minutes": loc.tz_offset_minutes,
        "location": {"lat": loc.lat, "lon": loc.lon},
        "peak_kw": loc.peak_kw,
        "pv_field": pv_field,
        "load_field": load_field,
        "bucket_minutes": BUCKET_MIN,
        "now_bucket": now_bucket,
        "days_of_history": days_of_history,
        "buckets": buckets,
    }


async def excess_today(
    history: History, serial: str, loc: LocationConfig, hist_days: int = 14
) -> dict:
    """Per-bucket production headroom and predicted excess for the day.

    For each 15-min bucket of today, we compute:

      * `clearsky_w`           — theoretical max from local solar position
      * `expected_max_w`       — observed max at that time-of-day across
                                  recent days (capped by clearsky to filter
                                  out spurious peaks); the realistic ceiling
                                  for *this* installation given orientation,
                                  shading, inverter clipping, etc.
      * `expected_load_w`      — historical average load at that bucket
                                  (this is where the AC time-of-day pattern
                                  shows up — hot afternoons run higher)
      * `actual_pv_w`          — today's actual so far
      * `actual_load_w`        — today's actual load so far
      * `excess_w`             — max(0, expected_max_w - expected_load_w);
                                  W you could deploy a load into without
                                  pulling from grid/battery

    Plus rollup tiles: now/peak/total-today.
    """
    pv_field = await pick_field(history, serial, PV_FIELD_CANDIDATES)
    load_field = await pick_field(history, serial, LOAD_FIELD_CANDIDATES)

    hist_pv_max: dict[int, float] = {}
    hist_pv_avg: dict[int, float] = {}
    today_pv: dict[int, float] = {}
    if pv_field:
        hist_pv_max = await history.bucket_max_by_time_of_day(
            serial, pv_field, days=hist_days, bucket_minutes=BUCKET_MIN,
            tz_offset_minutes=loc.tz_offset_minutes,
        )
        hist_pv_avg = await history.bucket_avg_by_time_of_day(
            serial, pv_field, days=hist_days, bucket_minutes=BUCKET_MIN,
            tz_offset_minutes=loc.tz_offset_minutes,
        )
        today_pv = await history.bucket_avg_by_time_of_day(
            serial, pv_field, days=1, bucket_minutes=BUCKET_MIN,
            tz_offset_minutes=loc.tz_offset_minutes,
        )

    hist_load_avg: dict[int, float] = {}
    today_load: dict[int, float] = {}
    if load_field:
        hist_load_avg = await history.bucket_avg_by_time_of_day(
            serial, load_field, days=hist_days, bucket_minutes=BUCKET_MIN,
            tz_offset_minutes=loc.tz_offset_minutes,
        )
        today_load = await history.bucket_avg_by_time_of_day(
            serial, load_field, days=1, bucket_minutes=BUCKET_MIN,
            tz_offset_minutes=loc.tz_offset_minutes,
        )

    now_local = _now_local(loc.tz_offset_minutes)
    now_bucket = _bucket_of(now_local)

    buckets = []
    for b in range(0, 24 * 60, BUCKET_MIN):
        bucket_dt_local = _bucket_to_dt(b, now_local)
        clearsky = clearsky_power_w(loc.lat, loc.lon, bucket_dt_local, loc.peak_kw)
        # Use the best observed PV at this bucket; fall back to clearsky if
        # we don't have history yet. Cap by clearsky to filter outliers.
        observed_max = hist_pv_max.get(b)
        if observed_max is not None and observed_max > 0:
            expected_max = min(observed_max, clearsky * 1.05)  # tiny grace for tilt benefit
        else:
            expected_max = clearsky
        expected_load = hist_load_avg.get(b) or 0.0
        excess = max(0.0, expected_max - expected_load)
        buckets.append({
            "minute_of_day": b,
            "clearsky_w": clearsky,
            "expected_max_w": expected_max,
            "historical_avg_pv_w": hist_pv_avg.get(b),
            "expected_load_w": expected_load,
            "actual_pv_w": today_pv.get(b) if b <= now_bucket else None,
            "actual_load_w": today_load.get(b) if b <= now_bucket else None,
            "excess_w": excess,
        })

    # Tiles
    hours = loc.peak_kw  # ratio factor for kWh estimates
    bucket_hours = BUCKET_MIN / 60
    total_excess_kwh = sum(b["excess_w"] for b in buckets) * bucket_hours / 1000

    # "Right now" — the current bucket
    cur = buckets[now_bucket // BUCKET_MIN] if buckets else None
    peak_excess = max(buckets, key=lambda b: b["excess_w"]) if buckets else None

    # Days of history covered
    days_of_history = 0
    if pv_field:
        first = await history.first_sample_ts(serial, pv_field)
        if first is not None:
            days_of_history = max(
                1, int((datetime.now(timezone.utc).timestamp() * 1000 - first) / 86_400_000)
            )

    return {
        "tz_offset_minutes": loc.tz_offset_minutes,
        "location": {"lat": loc.lat, "lon": loc.lon},
        "peak_kw": loc.peak_kw,
        "pv_field": pv_field,
        "load_field": load_field,
        "bucket_minutes": BUCKET_MIN,
        "now_bucket": now_bucket,
        "days_of_history": days_of_history,
        "buckets": buckets,
        "summary": {
            "now": cur,
            "peak_excess_bucket": peak_excess,
            "total_excess_today_kwh": total_excess_kwh,
        },
    }


async def max_production_envelope(loc: LocationConfig) -> list[dict]:
    """Pure theoretical clear-sky envelope for one local day."""
    # anchor at today's local midnight
    now_local = _now_local(loc.tz_offset_minutes)
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for b in range(0, 24 * 60, BUCKET_MIN):
        t = midnight + timedelta(minutes=b)
        out.append(
            {
                "minute_of_day": b,
                "clearsky_w": clearsky_power_w(loc.lat, loc.lon, t, loc.peak_kw),
            }
        )
    return out


async def battery_completion(
    history: History, serial: str, loc: LocationConfig
) -> dict:
    """Forward-integrate SoC at 5-min steps until 100% or 12h horizon.

    For each future step:
      net_w = expected_pv (from hist curve or clearsky) - expected_load - other_draws
      net_w is capped at +/- max_charge_kw * 1000
      delta_soc = net_w * step_s / 3600 / 1000 / capacity_kwh * 100

    If we have no historical curve yet, fall back to current empirical charge
    rate (dSoC/dt over last 30 min) held flat.
    """
    cur_soc = await soc_now(history, serial)
    if cur_soc is None:
        return {"reason": "no SoC samples yet — let the poller collect data for a few minutes."}
    if cur_soc >= 99.5:
        return {
            "current_soc_pct": cur_soc,
            "reason": "battery already full",
        }

    pv_field = await pick_field(history, serial, PV_FIELD_CANDIDATES)
    load_field = await pick_field(history, serial, LOAD_FIELD_CANDIDATES)
    hist_pv = await historical_curve(history, serial, pv_field, loc) if pv_field else {}
    hist_load = await historical_curve(history, serial, load_field, loc) if load_field else {}

    measured_rate = await soc_rate_per_min(history, serial)  # %/min
    if (not hist_pv and not measured_rate) or (
        measured_rate is not None and measured_rate <= 0 and not hist_pv
    ):
        return {
            "current_soc_pct": cur_soc,
            "measured_rate_pct_per_min": measured_rate,
            "reason": "not currently charging and no historical solar curve yet",
        }

    step_min = 5
    horizon_min = 12 * 60
    now_local = _now_local(loc.tz_offset_minutes)
    soc = cur_soc
    projection = [{"ts": int(now_local.astimezone(timezone.utc).timestamp() * 1000), "soc_pct": soc}]
    eta_local: Optional[datetime] = None

    for step in range(1, horizon_min // step_min + 1):
        t_local = now_local + timedelta(minutes=step * step_min)
        b = (t_local.hour * 60 + t_local.minute) // BUCKET_MIN * BUCKET_MIN

        if hist_pv:
            pv_w = hist_pv.get(b, 0.0)
        else:
            pv_w = clearsky_power_w(loc.lat, loc.lon, t_local, loc.peak_kw) * 0.6
        load_w = hist_load.get(b, 0.0) if hist_load else 0.0
        net_w = pv_w - load_w
        net_w = max(-loc.max_charge_kw * 1000, min(loc.max_charge_kw * 1000, net_w))

        # If we have no historical curve, fall back to the measured rate
        if not hist_pv and measured_rate is not None:
            delta_pct = measured_rate * step_min
        else:
            kwh_in = net_w * (step_min / 60) / 1000
            delta_pct = (kwh_in / loc.battery_capacity_kwh) * 100

        soc = max(0.0, min(100.0, soc + delta_pct))
        projection.append(
            {
                "ts": int(t_local.astimezone(timezone.utc).timestamp() * 1000),
                "soc_pct": round(soc, 2),
            }
        )
        if soc >= 100.0 and eta_local is None:
            eta_local = t_local
            break

    return {
        "current_soc_pct": round(cur_soc, 2),
        "measured_rate_pct_per_min": measured_rate,
        "eta_iso": eta_local.isoformat() if eta_local else None,
        "minutes_remaining": int((eta_local - now_local).total_seconds() / 60) if eta_local else None,
        "battery_capacity_kwh": loc.battery_capacity_kwh,
        "max_charge_kw": loc.max_charge_kw,
        "step_minutes": step_min,
        "projection": projection,
        "used_historical": bool(hist_pv),
    }
