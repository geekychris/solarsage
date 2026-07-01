"""SolarVitals widget — pretty formatting, projection math with real
battery capacity, EPS load fallback, per-string breakdown."""

from __future__ import annotations

import pytest

from app.widgets import solar_vitals as SV


def test_fmt_hours_minutes_variants():
    assert SV._fmt_hours_minutes(0.5) == "30 min"
    assert SV._fmt_hours_minutes(1.0) == "1 h"
    assert SV._fmt_hours_minutes(2.5) == "2 h 30 min"
    assert SV._fmt_hours_minutes(0.05) == "3 min"


def test_target_time_iso_is_iso8601():
    from datetime import datetime
    s = SV._target_time_iso(1.5)
    d = datetime.fromisoformat(s)
    assert d.tzinfo is not None


async def _seed_db(path, fields):
    """Write a minimal EG4 history schema + one sample per field."""
    import aiosqlite
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "CREATE TABLE samples (serial_num TEXT, ts INTEGER, "
            "category TEXT, field TEXT, value REAL)"
        )
        await db.execute("CREATE TABLE settings (key TEXT, value TEXT)")
        for f, v in fields.items():
            await db.execute(
                "INSERT INTO samples VALUES (?, ?, ?, ?, ?)",
                ("SN1", 1000000, "runtime", f, v),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_no_samples_returns_note(tmp_db_path):
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


@pytest.mark.asyncio
async def test_charging_uses_real_capacity(tmp_db_path):
    """The whole point of the fix — batCapacity Ah × 51.2 V is used
    for kWh, not the 14.3 default. 840 Ah × 51.2 V = 43 kWh."""
    await _seed_db(tmp_db_path, {
        "soc": 64.0,
        "ppv1": 4664.0,
        "ppv2": 1610.0,
        "ppv": 6274.0,
        "pCharge": 3910.0,
        "pDisCharge": 0.0,
        "pEpsL1N": 1098.0,
        "pEpsL2N": 1056.0,
        "batCapacity": 840.0,
        "consumptionPower": 0.0,   # broken on EPS-wired systems
    })
    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    data = await w.fetch(w.default_config)
    # Battery
    assert data["battery"]["soc"] == 64.0
    assert 40 < data["battery"]["capacity_kwh"] < 45
    assert "batCapacity" in data["battery"]["capacity_source"]
    # Solar total from ppv, strings populated
    assert data["solar"]["total_kw"] == 6.27
    assert len(data["solar"]["strings"]) == 2
    # Load — falls back to EPS phase sum because consumptionPower=0
    assert data["load"]["kw"] == 2.15
    assert "pEpsL1N" in (data["load"]["field"] or "")
    # Battery flow
    assert data["battery_flow"]["state"] == "charging"
    assert data["battery_flow"]["charge_kw"] == 3.91
    # Projection: (100 - 64)% × 43 kWh / 3.91 kW = ~3.96 h
    assert data["projection"]["direction"] == "charging"
    assert 3.5 < data["projection"]["hours"] < 4.3
    assert data["cut_back"] is None


@pytest.mark.asyncio
async def test_discharging_flags_cut_back(tmp_db_path):
    """At 50% SoC discharging 2 kW with a 43 kWh bank, cut-back at
    30% happens in (50-30)% × 43 / 2 = 4.3 h."""
    await _seed_db(tmp_db_path, {
        "soc": 50.0,
        "ppv": 0.0,
        "pCharge": 0.0,
        "pDisCharge": 2000.0,
        "pEpsL1N": 1000.0,
        "pEpsL2N": 1000.0,
        "batCapacity": 840.0,
        "consumptionPower": 2000.0,
    })
    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    data = await w.fetch(w.default_config)
    assert data["battery_flow"]["state"] == "discharging"
    assert data["projection"]["direction"] == "discharging"
    assert data["cut_back"] is not None
    assert 3.5 < data["cut_back"]["hours"] < 5.0
    assert data["cut_back"]["target_soc"] == 30


@pytest.mark.asyncio
async def test_load_breakdown_marks_unaccounted(tmp_db_path):
    """When actual load exceeds the sum of 'on' appliances, an
    'Unaccounted' slice appears."""
    await _seed_db(tmp_db_path, {
        "soc": 60.0,
        "pEpsL1N": 1000.0,
        "pEpsL2N": 1000.0,
        "batCapacity": 840.0,
    })
    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    cfg = {**w.default_config, "appliances": [
        {"name": "Baseline", "watts": 400, "on": True},
        {"name": "AC main", "watts": 3500, "on": False},
    ]}
    data = await w.fetch(cfg)
    names = [b["name"] for b in data["load"]["breakdown"]]
    assert "Baseline" in names
    assert "Unaccounted" in names


@pytest.mark.asyncio
async def test_smart_ac_scaled_to_fit_measured_load(tmp_db_path, monkeypatch):
    """When smart_ac rated watts overshoot the (load - manual) headroom,
    each AC slice is scaled proportionally so the pie balances to load."""
    await _seed_db(tmp_db_path, {
        "soc": 60.0,
        "pEpsL1N": 1500.0,
        "pEpsL2N": 1000.0,   # 2500 W measured load
        "batCapacity": 840.0,
    })
    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path

    # Stub _fetch_smart_ac so we don't need a real HA. Two ACs on with
    # 1400 + 1200 W rated = 2600 W — overshoots by 100 W after 400 W
    # of manual baseline is subtracted from 2500 W load → 2100 W headroom.
    async def fake_fetch(*a, **kw):
        return [
            {"room": "living", "name": "AC — Living", "entity_id": "input_boolean.ac_living",
             "watts": 1400, "on": True, "state": "on", "note": "ok"},
            {"room": "kyle",   "name": "AC — Kyle",   "entity_id": "input_boolean.ac_kyle",
             "watts": 1200, "on": True, "state": "on", "note": "ok"},
        ]
    monkeypatch.setenv("HA_URL", "http://fake")
    monkeypatch.setenv("HA_TOKEN", "fake")
    monkeypatch.setattr(SV, "_fetch_smart_ac", fake_fetch)

    w = SV.SolarVitalsWidget()
    cfg = {**w.default_config, "appliances": [
        {"name": "Baseline", "watts": 400, "on": True},
    ]}
    data = await w.fetch(cfg)
    slices = {b["name"]: b for b in data["load"]["breakdown"]}
    # Baseline is not scaled — user-declared manual
    assert slices["Baseline"]["watts"] == 400
    # ACs proportionally scaled: 2100 / 2600 = ~0.808
    assert slices["AC — Living"]["scale"] == round(2100 / 2600, 3)
    # 1400 * 0.808 ≈ 1131
    assert 1120 < slices["AC — Living"]["watts"] < 1140
    assert 960  < slices["AC — Kyle"]["watts"]   < 980
    # Rated watts preserved on the slice
    assert slices["AC — Living"]["rated_watts"] == 1400
    # Total should now match load (± rounding) — no Unaccounted / Over-estimated
    total = sum(b["watts"] for b in data["load"]["breakdown"])
    assert 2495 < total < 2505
    # Chip row also gets the scale
    living = next(r for r in data["load"]["smart_ac_rooms"] if r["room"] == "living")
    assert living["rated_watts"] == 1400
    assert living["scale"] < 1.0


@pytest.mark.asyncio
async def test_smart_ac_scaling_can_be_disabled(tmp_db_path, monkeypatch):
    await _seed_db(tmp_db_path, {
        "soc": 60.0, "pEpsL1N": 1000.0, "pEpsL2N": 500.0,
        "batCapacity": 840.0,
    })
    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path

    async def fake_fetch(*a, **kw):
        return [{"room": "living", "name": "AC — Living",
                 "entity_id": "input_boolean.ac_living",
                 "watts": 2000, "on": True, "state": "on", "note": "ok"}]
    monkeypatch.setenv("HA_URL", "http://fake")
    monkeypatch.setenv("HA_TOKEN", "fake")
    monkeypatch.setattr(SV, "_fetch_smart_ac", fake_fetch)

    w = SV.SolarVitalsWidget()
    cfg = {**w.default_config, "appliances": [],
           "scale_smart_ac_to_load": False}
    data = await w.fetch(cfg)
    slices = {b["name"]: b for b in data["load"]["breakdown"]}
    # AC keeps its full rated watts even though load is only 1500 W
    assert slices["AC — Living"]["watts"] == 2000
    assert slices["AC — Living"]["scale"] == 1.0
    # Over-estimated slice reflects the mismatch
    assert "Over-estimated" in slices


@pytest.mark.asyncio
async def test_capacity_falls_back_to_setting_without_batcapacity(tmp_db_path):
    """When EG4 doesn't report batCapacity, we still get kWh via the
    settings row."""
    import aiosqlite
    await _seed_db(tmp_db_path, {"soc": 50.0, "ppv": 1000.0})
    async with aiosqlite.connect(tmp_db_path) as db:
        await db.execute("INSERT INTO settings VALUES (?, ?)",
                         ("battery_capacity_kwh", "20"))
        await db.commit()
    import os
    os.environ["EG4_DB_PATH"] = tmp_db_path
    w = SV.SolarVitalsWidget()
    data = await w.fetch(w.default_config)
    assert data["battery"]["capacity_kwh"] == 20.0
    assert "settings" in data["battery"]["capacity_source"]
