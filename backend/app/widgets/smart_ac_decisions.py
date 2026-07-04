"""Smart AC decisions-log widget.

Tails the smart_ac scheduler's JSONL decision log (one entry every 5-min
tick) and surfaces the last N decisions on the dashboard. Read-only — the
smart_ac app owns the log; we just present it.

Log path is env-configurable (``SMART_AC_DECISIONS_LOG``) with a
sensible default matching the layout on pi-sf:

    /home/chris/smart_ac/decisions.log

Each JSONL line looks like::

    {"ts": "...", "mode": "ON_TRACK", "soc": 61.0,
     "battery_power_w": 3918, "pv_power_w": 5723, "load_w": 1805,
     "outdoor_f": 93.6, "indoor_f": {"living": 82.5, "master": 80.5},
     "ac_on": {"master": false, "living": true, ...},
     "target": {...}, "target_on": ["living"],
     "actions": [{"action":"ON","room":"living","reason":"..."}],
     "reasons": {"master": "...", ...}, "enabled": true,
     "unoccupied": false}

We normalize + trim to a compact structure the frontend can render
without re-parsing.
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any

from .base import Widget

log = logging.getLogger("eg4.widgets.smart_ac_decisions")

DEFAULT_LOG_PATH = "/home/chris/smart_ac/decisions.log"
DEFAULT_LIMIT = 25
READ_TAIL_BYTES = 128 * 1024  # 128 KB is well over `DEFAULT_LIMIT` decisions


def _tail_lines(path: str, max_lines: int, read_bytes: int) -> list[str]:
    """Read the last ~read_bytes of a file and return up to max_lines
    complete newline-terminated lines. Cheap for a growing log file since
    we never load the whole thing."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > read_bytes:
            f.seek(size - read_bytes)
            # Skip any partial first line
            f.readline()
        chunk = f.read()
    text = chunk.decode("utf-8", errors="replace")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return lines


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """Trim to the fields the frontend renders. Keeps payload small."""
    actions = entry.get("actions") or []
    return {
        "ts": entry.get("ts"),
        "mode": entry.get("mode"),
        "soc": entry.get("soc"),
        "battery_power_w": entry.get("battery_power_w"),
        "pv_power_w": entry.get("pv_power_w"),
        "load_w": entry.get("load_w"),
        "outdoor_f": entry.get("outdoor_f"),
        "indoor_f": entry.get("indoor_f") or {},
        "ac_on": entry.get("ac_on") or {},
        "target_on": entry.get("target_on") or [],
        "actions": actions,
        "reasons": entry.get("reasons") or {},
        "enabled": entry.get("enabled"),
        "unoccupied": entry.get("unoccupied"),
        "has_actions": len(actions) > 0,
    }


class SmartAcDecisionsWidget(Widget):
    id = "smart_ac_decisions"
    kind = "smart_ac_decisions"
    name = "Smart AC decisions"
    description = (
        "Tail of the smart_ac scheduler's decisions log — the last N ticks "
        "with mode, SoC, per-room state + reasons, and any actions taken. "
        "Read-only mirror of /home/chris/smart_ac/decisions.log."
    )
    refresh_seconds = 60
    default_tab = "Solar"
    default_position = 5
    default_width = 2

    config_schema = {
        "type": "object",
        "properties": {
            "log_path": {"type": "string"},
            "limit": {"type": "integer", "minimum": 5, "maximum": 200},
        },
    }
    default_config = {
        "log_path": "",  # empty → env or hardcoded default
        "limit": DEFAULT_LIMIT,
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        path = (
            (config.get("log_path") or "").strip()
            or os.getenv("SMART_AC_DECISIONS_LOG")
            or DEFAULT_LOG_PATH
        )
        limit = int(config.get("limit") or DEFAULT_LIMIT)
        limit = max(5, min(200, limit))

        if not os.path.exists(path):
            return {
                "note": f"decisions log not found: {path}",
                "log_path": path,
                "decisions": [],
            }

        try:
            raw_lines = _tail_lines(path, max_lines=limit, read_bytes=READ_TAIL_BYTES)
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to tail %s: %s", path, exc)
            return {
                "note": f"could not read log: {exc}",
                "log_path": path,
                "decisions": [],
            }

        decisions: list[dict[str, Any]] = []
        for line in raw_lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                decisions.append(_normalize(entry))

        decisions.reverse()  # newest first

        latest = decisions[0] if decisions else None
        return {
            "log_path": path,
            "size_bytes": os.path.getsize(path),
            "latest_ts": latest["ts"] if latest else None,
            "latest_mode": latest["mode"] if latest else None,
            "latest_soc": latest["soc"] if latest else None,
            "on_rooms": (
                [r for r, v in (latest.get("ac_on") or {}).items() if v]
                if latest else []
            ),
            "count": len(decisions),
            "decisions": decisions,
        }
