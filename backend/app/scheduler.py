"""Find when to run discretionary appliances based on the surplus forecast.

For each deferrable, enabled appliance, scan tomorrow's hourly surplus forecast
and return the earliest start time where the rolling surplus over the
appliance's runtime ≥ its watts. Results ranked by total expected surplus over
the window.

This is the "smart load scheduler" feature: turns the abstract excess kWh
number into concrete "run X at 11:30 tomorrow" recommendations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _hour_to_bucket_index(hour_offset: int) -> int:
    return hour_offset


def schedule_appliances(
    appliances: list[dict[str, Any]],
    hourly_forecast: list[dict[str, Any]],
    tz_offset_minutes: int,
) -> list[dict[str, Any]]:
    """`hourly_forecast` rows must have `predicted_surplus_w` and `time` (ISO)."""
    if not hourly_forecast:
        return []
    # Only look ahead of "now"
    now_utc = datetime.now(timezone.utc)
    upcoming: list[dict[str, Any]] = []
    for r in hourly_forecast:
        try:
            t = datetime.strptime(r["time"], "%Y-%m-%dT%H:%M")
            t = t.replace(tzinfo=timezone(timedelta(minutes=tz_offset_minutes)))
        except Exception:
            continue
        if t.astimezone(timezone.utc) >= now_utc:
            upcoming.append({**r, "_dt": t})
    if len(upcoming) < 2:
        return []

    out: list[dict[str, Any]] = []
    for appl in appliances:
        if not appl.get("enabled") or not appl.get("can_defer"):
            continue
        watts = float(appl["watts"])
        runtime_min = int(appl["typical_minutes"])
        runtime_hours = max(1, (runtime_min + 59) // 60)  # round up to whole hours
        pref_s = appl.get("preferred_start_hour")
        pref_e = appl.get("preferred_end_hour")

        # Slide a window of runtime_hours across upcoming hours
        best = None
        for i in range(0, len(upcoming) - runtime_hours + 1):
            window = upcoming[i : i + runtime_hours]
            # Require every hour in the window to clear the appliance's watts
            mins = [w.get("predicted_surplus_w") or 0 for w in window]
            if min(mins) < watts:
                continue
            # Optional: prefer windows inside preferred hour range
            start_h = window[0]["_dt"].hour
            end_h = window[-1]["_dt"].hour
            if pref_s is not None and pref_e is not None:
                # Skip windows that fall entirely outside preferred range
                if end_h < pref_s or start_h > pref_e:
                    continue
            total_surplus = sum(mins) * 1  # kWh-ish at hourly granularity / 1000
            avg_surplus = sum(mins) / len(mins)
            score = avg_surplus  # higher = better fit
            entry = {
                "appliance_id": appl.get("id"),
                "appliance_name": appl["name"],
                "watts_required": watts,
                "runtime_minutes": runtime_min,
                "start_iso": window[0]["_dt"].isoformat(),
                "end_iso": (window[-1]["_dt"] + timedelta(hours=1)).isoformat(),
                "average_surplus_w": avg_surplus,
                "minimum_surplus_w": min(mins),
                "score": score,
            }
            if best is None or entry["average_surplus_w"] > best["average_surplus_w"]:
                best = entry
        if best:
            out.append(best)
        else:
            out.append({
                "appliance_id": appl.get("id"),
                "appliance_name": appl["name"],
                "watts_required": watts,
                "runtime_minutes": runtime_min,
                "start_iso": None,
                "end_iso": None,
                "average_surplus_w": None,
                "minimum_surplus_w": None,
                "score": -1,
                "reason": "no window with sustained surplus ≥ appliance watts in forecast",
            })

    # Sort: viable windows first, ranked by surplus; non-viable at bottom
    out.sort(key=lambda e: (e["score"] is None, -(e["score"] or -1e9)))
    return out
