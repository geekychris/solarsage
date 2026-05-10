# SolarSage MCP server

Exposes SolarSage's REST API as MCP tools so any MCP-capable LLM client can
query your solar data with structured tool calls.

## Install

```bash
pip install "mcp[cli]" httpx
```

## Run

```bash
SOLARSAGE_BASE=http://127.0.0.1:8000 \
SOLARSAGE_API_KEY=local-dev-key-change-me \
python -m mcp_server.server
```

## Register with Claude Code

```bash
mkdir -p .mcp
cat > .mcp/solarsage.json <<'EOF'
{
  "command": "python",
  "args": ["-m", "mcp_server.server"],
  "env": {
    "SOLARSAGE_BASE": "http://127.0.0.1:8000",
    "SOLARSAGE_API_KEY": "local-dev-key-change-me",
    "PYTHONPATH": "."
  }
}
EOF
```

Then `/mcp` inside Claude Code will list the SolarSage tools and you can ask
Claude things like *"how many kWh did I produce yesterday?"* and it'll call
the right tool directly instead of curl-ing the API.

## Tools exposed

| Tool | Purpose |
| --- | --- |
| `list_sites` | All configured sites across vendors |
| `aggregate(serial, field, days, group_by, fn)` | Generic bucketed query |
| `summary(serial, days)` | Daily totals + best/worst |
| `best_day(serial, field, direction)` | Top-N days by any metric |
| `range_data(serial, days, fields)` | Multi-channel time series |
| `forecast_tomorrow(serial)` | Weather-aware tomorrow forecast |
| `forecast_excess(serial)` | Today's expected production headroom |
| `battery_completion(serial)` | When will battery hit 100%? |
| `schedule(serial, site_id)` | Smart load-scheduler recommendations |
| `string_health(serial, days)` | Per-string PV imbalance |
| `performance(serial, days)` | Actual vs expected kWh trend |
| `weather(days)` | Open-Meteo forecast |
| `list_alerts(site_id, unack_only)` | Anomaly alerts |
