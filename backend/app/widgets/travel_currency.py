"""MXN/USD currency widget — Frankfurter API (free, no key).

Frankfurter sources its rates from the ECB. Returns latest USD/MXN and a
short trailing series for a sparkline.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import aiohttp

from .base import Widget

LATEST_URL = "https://api.frankfurter.app/latest"
TIMESERIES_URL = "https://api.frankfurter.app/{start}..{end}"


class CurrencyWidget(Widget):
    id = "currency"
    kind = "currency"
    name = "MXN/USD"
    description = (
        "Daily USD/MXN rate from Frankfurter (ECB data), with a 14-day "
        "trailing series. Useful for cross-border budgeting."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Travel"
    default_position = 20

    config_schema = {
        "type": "object",
        "properties": {
            "base": {"type": "string"},
            "quotes": {"type": "array", "items": {"type": "string"}},
            "days": {"type": "integer", "minimum": 1, "maximum": 90},
        },
    }
    default_config = {"base": "USD", "quotes": ["MXN", "CAD"], "days": 14}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        base = str(config.get("base", "USD")).upper()
        quotes = [str(q).upper() for q in config.get("quotes") or ["MXN"]]
        days = int(config.get("days", 14))
        end = date.today()
        start = end - timedelta(days=days)
        params = {"from": base, "to": ",".join(quotes)}
        async with aiohttp.ClientSession() as http:
            async with http.get(LATEST_URL, params=params, timeout=30) as r:
                r.raise_for_status()
                latest = await r.json()
            ts_url = TIMESERIES_URL.format(start=start, end=end)
            async with http.get(ts_url, params=params, timeout=30) as r:
                r.raise_for_status()
                series = await r.json()
        # Reformat timeseries into per-quote arrays
        per_quote: dict[str, list[dict[str, Any]]] = {q: [] for q in quotes}
        for day, rates in sorted((series.get("rates") or {}).items()):
            for q in quotes:
                if q in rates:
                    per_quote[q].append({"date": day, "rate": rates[q]})
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "base": base,
            "latest_date": latest.get("date"),
            "latest": latest.get("rates") or {},
            "series": per_quote,
        }
