"""Tiny cooling-degree AC model.

Hypothesis: house load by hour-of-day ≈
    base_load(hour) + cooling_factor * max(0, outdoor_temp - threshold)

We fit a single threshold + single slope via grid search across a small range
(simple, robust, no scipy dependency). We separate the *base* (non-AC) load
per hour-of-day from the *AC* contribution per °F above threshold.

Given an hourly forecast of outdoor temp, we can then predict load.

This is intentionally simple — with weeks of data, ridge regression with
per-hour interactions would be sharper, but the gain is modest for residential
AC where cooling power tracks ΔT linearly over the comfort range.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .storage import History

log = logging.getLogger("eg4.ac_model")


@dataclass
class ACModel:
    threshold_f: float
    slope_w_per_f: float
    base_by_hour: dict[int, float]  # hour -> base load watts
    days_used: int
    correlation: float
    pv_field: str | None
    load_field: str | None

    def predict_load(self, hour: int, outdoor_temp_f: float) -> float:
        base = self.base_by_hour.get(hour, 0.0)
        ac = self.slope_w_per_f * max(0.0, outdoor_temp_f - self.threshold_f)
        return base + ac


async def fit_ac_model(
    history: History,
    serial: str,
    weather_hourly: dict,
    tz_offset_minutes: int,
    load_field: str,
) -> ACModel | None:
    """Fit the model from historical load + historical hourly temp.

    `weather_hourly` is the `hourly` block of an Open-Meteo *archive* response.
    Both sources are aligned on local hour-of-day timestamps.
    """
    times = weather_hourly.get("time") or []
    temps = weather_hourly.get("temperature_2m") or []
    if not times or len(times) != len(temps):
        return None

    # Index: local-hour-of-day -> list of (temp_f, hour_label_iso)
    from collections import defaultdict
    temp_by_hour_iso: dict[str, float] = {}
    for t, temp in zip(times, temps):
        if temp is None:
            continue
        # ISO local time like "2026-05-08T14:00"
        temp_by_hour_iso[t[:13] + ":00"] = float(temp)

    if not temp_by_hour_iso:
        return None

    # Pull load samples for the same time range, aggregate to per-hour averages
    # using the existing aggregate() with group_by=hour in local tz.
    from datetime import datetime, timedelta, timezone as _tz
    first_iso = min(temp_by_hour_iso.keys())
    last_iso = max(temp_by_hour_iso.keys())
    def _iso_to_utc_ms(iso: str) -> int:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M")
        return int(dt.replace(tzinfo=_tz(timedelta(minutes=tz_offset_minutes))).astimezone(_tz.utc).timestamp() * 1000)
    start_ms = _iso_to_utc_ms(first_iso)
    end_ms = _iso_to_utc_ms(last_iso) + 3600_000

    load_rows = await history.aggregate(
        serial, load_field, start_ms, end_ms,
        group_by="hour", fn="avg", tz_offset_minutes=tz_offset_minutes,
    )
    # Match by local "YYYY-MM-DD HH" → temp comes in "YYYY-MM-DDTHH"
    load_by_local_hour: dict[str, float] = {
        r["bucket"]: r["value"] for r in load_rows
        if r.get("value") is not None
    }
    if not load_by_local_hour:
        return None

    # Build paired dataset: temp_f, hour_of_day, load_w
    pairs: list[tuple[float, int, float]] = []
    for iso, t_f in temp_by_hour_iso.items():
        # iso = "YYYY-MM-DDTHH:00" — load bucket label is "YYYY-MM-DD HH"
        key = iso[:10] + " " + iso[11:13]
        load_w = load_by_local_hour.get(key)
        if load_w is None:
            continue
        hour = int(iso[11:13])
        pairs.append((t_f, hour, load_w))

    if len(pairs) < 24:
        log.info("ac_model: only %d paired samples, skipping", len(pairs))
        return None

    # Per-hour base load = MIN observed across days at that hour (the AC-free baseline)
    # then refine: try thresholds + slopes, pick combo with best R²
    from collections import defaultdict as _dd
    by_hour: dict[int, list[tuple[float, float]]] = _dd(list)
    for t_f, h, l in pairs:
        by_hour[h].append((t_f, l))

    base_by_hour: dict[int, float] = {}
    for h, vals in by_hour.items():
        # Base = lowest load seen at this hour (assumed to be AC-off baseline)
        base_by_hour[h] = min(v[1] for v in vals)

    # Residuals (load - base) vs (temp - threshold)
    # Grid-search threshold from 60..85 F, slope auto-fit by OLS on residuals
    def fit_slope(threshold: float) -> tuple[float, float]:
        """Return (slope, sse). slope = best W per °F above threshold."""
        xs, ys = [], []
        for t_f, h, l in pairs:
            x = max(0.0, t_f - threshold)
            y = l - base_by_hour.get(h, 0.0)
            xs.append(x)
            ys.append(y)
        sx2 = sum(x * x for x in xs)
        if sx2 == 0:
            return 0.0, sum(y * y for y in ys)
        slope = sum(x * y for x, y in zip(xs, ys)) / sx2
        sse = sum((y - slope * x) ** 2 for x, y in zip(xs, ys))
        return slope, sse

    best = (1e18, 75.0, 0.0)  # (sse, threshold, slope)
    for thr_int in range(50, 91):
        slope, sse = fit_slope(float(thr_int))
        if sse < best[0]:
            best = (sse, float(thr_int), slope)

    # Pearson r
    mean_l = sum(l for _, _, l in pairs) / len(pairs)
    tss = sum((l - mean_l) ** 2 for _, _, l in pairs)
    r_sq = 1 - (best[0] / tss) if tss > 0 else 0.0

    days_used = (len(times) // 24) if times else 0

    return ACModel(
        threshold_f=best[1],
        slope_w_per_f=max(0.0, best[2]),  # AC can't reduce load below base
        base_by_hour=base_by_hour,
        days_used=days_used,
        correlation=r_sq,
        pv_field=None,  # filled in by caller if relevant
        load_field=load_field,
    )
