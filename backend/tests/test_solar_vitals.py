"""SolarVitals widget — pretty formatting, projection math."""

from __future__ import annotations

import pytest

from app.widgets import solar_vitals as SV


def test_fmt_hours_minutes_variants():
    assert SV._fmt_hours_minutes(0.5) == "30 min"
    assert SV._fmt_hours_minutes(1.0) == "1 h"
    assert SV._fmt_hours_minutes(2.5) == "2 h 30 min"
    assert SV._fmt_hours_minutes(0.05) == "3 min"


def test_target_time_iso_is_iso8601():
    """Just confirm the string parses back to a datetime."""
    from datetime import datetime
    s = SV._target_time_iso(1.5)
    # If it round-trips through fromisoformat we're happy
    d = datetime.fromisoformat(s)
    assert d.tzinfo is not None


@pytest.mark.asyncio
async def test_fetch_returns_note_when_no_samples(tmp_db_path):
    """With an empty history table the widget just says 'no samples'
    instead of blowing up."""
    import aiosqlite
    async with aiosqlite.connect(tmp_db_path) as db:
        await db.execute(
            "CREATE TABLE samples (serial_num TEXT, ts INTEGER, "
            "category TEXT, field TEXT, value REAL)"
        )
        await db.execute("CREATE TABLE settings (key TEXT, value TEXT)")
        await db.commit()

    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    data = await w.fetch(w.default_config)
    assert "note" in data
    assert "no EG4 samples" in data["note"]


@pytest.mark.asyncio
async def test_fetch_computes_projection_when_charging(tmp_db_path):
    """Seed a history DB with SoC=50%, PV=5kW, load=2kW → charging,
    should hit 100% in a bounded time."""
    import aiosqlite
    async with aiosqlite.connect(tmp_db_path) as db:
        await db.execute(
            "CREATE TABLE samples (serial_num TEXT, ts INTEGER, "
            "category TEXT, field TEXT, value REAL)"
        )
        await db.execute("CREATE TABLE settings (key TEXT, value TEXT)")
        # Latest sample per field
        for field, value in (
            ("soc", 50.0),
            ("ppv", 5000.0),
            ("consumptionPower", 2000.0),
        ):
            await db.execute(
                "INSERT INTO samples VALUES (?, ?, ?, ?, ?)",
                ("SN1", 1000000, "runtime", field, value),
            )
        await db.execute(
            "INSERT INTO settings VALUES (?, ?)",
            ("battery_capacity_kwh", "10"),
        )
        await db.commit()

    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    data = await w.fetch(w.default_config)
    assert data["soc"] == 50.0
    assert data["pv_kw"] == 5.0
    assert data["load_kw"] == 2.0
    assert data["net_kw"] == 3.0
    assert data["state"] == "charging"
    # (100 - 50)% × 10 kWh / 3 kW = 1.6667 h
    assert data["projection"]["direction"] == "charging"
    assert 1.5 < data["projection"]["hours"] < 1.8
    assert data["cut_back"] is None   # not discharging


@pytest.mark.asyncio
async def test_fetch_flags_cut_back_when_discharging(tmp_db_path):
    """SoC=50%, PV=0, load=2kW → discharging, cut-back at 30% within
    a bounded time."""
    import aiosqlite
    async with aiosqlite.connect(tmp_db_path) as db:
        await db.execute(
            "CREATE TABLE samples (serial_num TEXT, ts INTEGER, "
            "category TEXT, field TEXT, value REAL)"
        )
        await db.execute("CREATE TABLE settings (key TEXT, value TEXT)")
        for field, value in (
            ("soc", 50.0),
            ("ppv", 0.0),
            ("consumptionPower", 2000.0),
        ):
            await db.execute(
                "INSERT INTO samples VALUES (?, ?, ?, ?, ?)",
                ("SN1", 1000000, "runtime", field, value),
            )
        await db.execute(
            "INSERT INTO settings VALUES (?, ?)",
            ("battery_capacity_kwh", "10"),
        )
        await db.commit()

    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    data = await w.fetch(w.default_config)
    assert data["state"] == "discharging"
    assert data["projection"]["direction"] == "discharging"
    assert data["cut_back"] is not None
    # (50 - 30)% × 10 kWh / 2 kW = 1.0 h
    assert 0.9 < data["cut_back"]["hours"] < 1.2
    assert data["cut_back"]["target_soc"] == 30
