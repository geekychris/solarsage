"""SolarSage MCP server.

Wraps the SolarSage REST API as MCP tools so any MCP-capable LLM (Claude
Code, Claude Desktop, etc.) can query the data with structured tool calls
instead of curl + json parsing.

Usage:
    pip install "mcp[cli]" httpx
    SOLARSAGE_BASE=http://127.0.0.1:8000 SOLARSAGE_API_KEY=... \
        python -m mcp_server.server

Register with Claude Code (project-local):
    mkdir -p .mcp
    cat > .mcp/solarsage.json <<EOF
    {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "SOLARSAGE_BASE": "http://127.0.0.1:8000",
        "SOLARSAGE_API_KEY": "local-dev-key-change-me"
      }
    }
    EOF
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

BASE = os.getenv("SOLARSAGE_BASE", "http://127.0.0.1:8000")
API_KEY = os.getenv("SOLARSAGE_API_KEY", "local-dev-key-change-me")

mcp = FastMCP("SolarSage")


async def _get(path: str, params: dict | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30, verify=False) as c:
        r = await c.get(f"{BASE}{path}", params=params, headers={"X-API-Key": API_KEY})
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def list_sites() -> dict:
    """List all configured solar sites (multi-vendor)."""
    return await _get("/api/sites")


@mcp.tool()
async def list_inverters(site_id: str = "site-1") -> dict:
    """List inverters / serial numbers for a site."""
    # /api/inverters uses the bearer-token EG4 session; for now we surface
    # serials from stored samples
    sites = (await _get("/api/sites")).get("sites", [])
    return {"sites_known": [s["id"] for s in sites]}


@mcp.tool()
async def aggregate(
    serial: str,
    field: str = "ppv",
    days: int = 7,
    group_by: str = "day",
    fn: str = "avg",
) -> dict:
    """Bucketed aggregation of any field over time.

    field: e.g. ppv, consumptionPower, soc, peps, pCharge, pDisCharge, pToGrid.
    group_by: minute | hour | day | week | month | none.
    fn: avg | sum | min | max | count.
    """
    return await _get(
        "/api/aggregate",
        params={"serial": serial, "field": field, "days": days,
                "group_by": group_by, "fn": fn},
    )


@mcp.tool()
async def summary(serial: str, days: int = 30) -> dict:
    """Roll-up of daily kWh totals and best/worst solar days."""
    return await _get("/api/summary", params={"serial": serial, "days": days})


@mcp.tool()
async def best_day(serial: str, field: str = "ppv", direction: str = "best",
                   days: int = 365, n: int = 10) -> dict:
    """Top-N days by any metric. direction: best | worst."""
    return await _get(
        "/api/best_day",
        params={"serial": serial, "field": field, "direction": direction,
                "days": days, "n": n},
    )


@mcp.tool()
async def range_data(serial: str, days: float = 7,
                     fields: str = "ppv,consumptionPower,soc,pCharge,pDisCharge,peps") -> dict:
    """Multi-channel time series with auto bucketing."""
    return await _get(
        "/api/range",
        params={"serial": serial, "days": days, "fields": fields},
    )


@mcp.tool()
async def forecast_tomorrow(serial: str) -> dict:
    """Weather-aware tomorrow forecast: hourly PV, AC, load, surplus."""
    return await _get("/api/forecast/tomorrow", params={"serial": serial})


@mcp.tool()
async def forecast_excess(serial: str) -> dict:
    """Today's expected production headroom (max producible − expected load)."""
    return await _get("/api/forecast/excess", params={"serial": serial})


@mcp.tool()
async def battery_completion(serial: str) -> dict:
    """When will the battery hit 100%? Projected SoC trajectory included."""
    return await _get("/api/forecast/battery_completion", params={"serial": serial})


@mcp.tool()
async def schedule(serial: str, site_id: str = "site-1") -> dict:
    """Smart load-scheduler recommendations for enabled appliances."""
    return await _get("/api/schedule", params={"serial": serial, "site_id": site_id})


@mcp.tool()
async def string_health(serial: str, days: int = 14) -> dict:
    """Per-string PV ratio — flags strings producing far below the strongest."""
    return await _get("/api/string_health", params={"serial": serial, "days": days})


@mcp.tool()
async def performance(serial: str, days: int = 30) -> dict:
    """Actual vs irradiance-expected daily kWh — degradation trend."""
    return await _get("/api/performance", params={"serial": serial, "days": days})


@mcp.tool()
async def weather(days: int = 7) -> dict:
    """Open-Meteo weather forecast for the configured site (temp, GHI, cloud, etc.)."""
    return await _get("/api/weather", params={"days": days})


@mcp.tool()
async def list_alerts(site_id: str = "site-1", unack_only: bool = False) -> dict:
    """Active alerts from the anomaly watcher."""
    return await _get(
        "/api/alerts",
        params={"site_id": site_id, "unacknowledged_only": unack_only},
    )


if __name__ == "__main__":
    mcp.run()
