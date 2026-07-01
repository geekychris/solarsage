"""Auto-announcements — tide extremes become events with per-channel
reminders sourced from config."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from app import announcements as ann
from app.events.store import EventStore
from app.widgets.base import WidgetState
from app.widgets.store import WidgetStore


@pytest.mark.asyncio
async def test_merged_config_fills_defaults():
    cfg = ann.merged_config(None)
    assert cfg["tides"]["enabled"] is False
    assert cfg["tides"]["warn_minutes_before"] == [120, 30]

    cfg2 = ann.merged_config({"tides": {"enabled": True, "channels": ["telegram"]}})
    assert cfg2["tides"]["enabled"] is True
    assert cfg2["tides"]["channels"] == ["telegram"]
    # Defaults still apply for unspecified fields
    assert cfg2["tides"]["warn_minutes_before"] == [120, 30]


@pytest.mark.asyncio
async def test_ingest_tide_events_creates_events(tmp_db_path):
    ev_store = EventStore(tmp_db_path)
    await ev_store.init()
    ws = WidgetStore(tmp_db_path)
    await ws.init()

    # Two extremes: one inside the horizon, one past the horizon
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(hours=2)).replace(microsecond=0).isoformat()
    later = (now + timedelta(hours=100)).replace(microsecond=0).isoformat()
    tide_data = {
        "stations": [{
            "id": "san_felipe", "name": "San Felipe",
            "extremes": [
                {"dt": 0, "iso": soon,  "height_m": 1.42, "type": "High"},
                {"dt": 0, "iso": later, "height_m": 0.10, "type": "Low"},
            ],
        }],
    }
    await ws.put_state("tides", WidgetState(
        fetched_at=time.time(), data=tide_data, error=None,
    ))

    cfg = {"tides": {
        "enabled": True,
        "warn_minutes_before": [60, 30],
        "channels": ["tts", "telegram"],
        "types": ["high", "low"],
        "stations": [],
    }}
    n = await ann.ingest_tide_events(ev_store, ws, cfg)
    assert n == 1  # only the in-horizon one

    events = await ev_store.list_events(
        starts_after=now.isoformat(),
    )
    tides = [e for e in events if e.source == "tide"]
    assert len(tides) == 1
    tev = tides[0]
    assert "San Felipe" in tev.title
    assert "high" in tev.title.lower()
    # 2 offsets × combined mode → 2 reminders (channels collapsed to mode)
    assert len(tev.reminders) == 2
    modes = {r.mode for r in tev.reminders}
    assert modes == {"tts+telegram"}
    offsets = sorted(r.minutes_before for r in tev.reminders)
    assert offsets == [30, 60]


@pytest.mark.asyncio
async def test_ingest_disabled_source_creates_nothing(tmp_db_path):
    ev_store = EventStore(tmp_db_path)
    await ev_store.init()
    ws = WidgetStore(tmp_db_path)
    await ws.init()

    soon = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await ws.put_state("tides", WidgetState(
        fetched_at=time.time(),
        data={"stations": [{
            "id": "san_felipe", "name": "SF",
            "extremes": [{"dt": 0, "iso": soon, "height_m": 1.0, "type": "High"}],
        }]},
        error=None,
    ))

    n = await ann.ingest_tide_events(ev_store, ws, {"tides": {"enabled": False}})
    assert n == 0


@pytest.mark.asyncio
async def test_ingest_station_filter(tmp_db_path):
    ev_store = EventStore(tmp_db_path)
    await ev_store.init()
    ws = WidgetStore(tmp_db_path)
    await ws.init()

    soon = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    await ws.put_state("tides", WidgetState(
        fetched_at=time.time(),
        data={"stations": [
            {"id": "san_felipe", "name": "SF",
             "extremes": [{"dt": 0, "iso": soon, "height_m": 1.0, "type": "High"}]},
            {"id": "puertecitos", "name": "PU",
             "extremes": [{"dt": 0, "iso": soon, "height_m": 1.1, "type": "Low"}]},
        ]},
        error=None,
    ))

    cfg = {"tides": {
        "enabled": True, "warn_minutes_before": [15],
        "channels": ["tts"], "types": ["high", "low"],
        "stations": ["puertecitos"],
    }}
    n = await ann.ingest_tide_events(ev_store, ws, cfg)
    assert n == 1
