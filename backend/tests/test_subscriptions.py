"""Subscription store + rule evaluator."""

from __future__ import annotations

import pytest

from app import subscriptions as S
from app import notify as _n


# --- path lookup + condition eval ----------------------------------------

def test_get_by_path_dotted():
    data = {"a": {"b": {"c": 42}}}
    assert S._get_by_path(data, "a.b.c") == 42
    assert S._get_by_path(data, "a.b.missing") is None
    assert S._get_by_path(data, "") == data


def test_get_by_path_with_index():
    data = {"ports": [{"delay": 30}, {"delay": 60}]}
    assert S._get_by_path(data, "ports[0].delay") == 30
    assert S._get_by_path(data, "ports[1].delay") == 60
    assert S._get_by_path(data, "ports[9].delay") is None


def test_get_by_path_nested_index():
    data = {"stations": [{"extremes": [{"height_m": 1.5}, {"height_m": -2.3}]}]}
    assert S._get_by_path(data, "stations[0].extremes[0].height_m") == 1.5
    assert S._get_by_path(data, "stations[0].extremes[1].height_m") == -2.3


def test_cmp_numeric():
    assert S._cmp(101, ">", 100) is True
    assert S._cmp(100, ">", 100) is False
    assert S._cmp(100, ">=", 100) is True
    assert S._cmp(50, "<", 100) is True
    assert S._cmp("42", ">", 41) is True   # coerced


def test_cmp_string_ops():
    assert S._cmp("hello world", "contains", "world") is True
    assert S._cmp("hola", "contains", "world") is False
    assert S._cmp("hola", "not_contains", "world") is True
    assert S._cmp("HOLA", "contains", "hola") is True   # case-insensitive


def test_cmp_none_never_matches():
    for op in (">", "<", "==", "contains"):
        assert S._cmp(None, op, 5) is False


def test_cmp_type_mismatch_safe():
    assert S._cmp("banana", ">", 5) is False


def test_evaluate_condition_returns_matched_and_actual():
    data = {"current": {"us_aqi": 120}}
    cond = {"path": "current.us_aqi", "op": ">", "value": 100}
    matched, actual = S.evaluate_condition(data, cond)
    assert matched is True
    assert actual == 120


def test_evaluate_condition_no_match():
    data = {"current": {"us_aqi": 42}}
    cond = {"path": "current.us_aqi", "op": ">", "value": 100}
    matched, actual = S.evaluate_condition(data, cond)
    assert matched is False
    assert actual == 42


def test_render_message_substitutes_paths():
    data = {"a": 5, "b": {"c": "hola"}}
    assert S.render_message("val is {a}, nested is {b.c}", data) == "val is 5, nested is hola"


def test_render_message_missing_paths_empty():
    data = {"a": 1}
    assert S.render_message("a={a} b={missing.field}", data) == "a=1 b="


# --- store CRUD + evaluate_and_fire --------------------------------------

@pytest.mark.asyncio
async def test_store_init_and_upsert(tmp_db_path):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    saved = await store.upsert({
        "widget_id": "aqi",
        "name": "test",
        "condition": {"path": "x", "op": ">", "value": 1},
        "actions": [{"type": "log"}],
    })
    assert saved["id"]
    assert saved["widget_id"] == "aqi"
    assert saved["rule"]["name"] == "test"


@pytest.mark.asyncio
async def test_upsert_missing_widget_id_raises(tmp_db_path):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    with pytest.raises(ValueError):
        await store.upsert({"name": "no widget"})


@pytest.mark.asyncio
async def test_upsert_update_preserves_created_at(tmp_db_path):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    a = await store.upsert({"widget_id": "aqi", "name": "v1"})
    import asyncio; await asyncio.sleep(0.01)
    b = await store.upsert({"id": a["id"], "widget_id": "aqi", "name": "v2"})
    assert b["id"] == a["id"]
    assert b["rule"]["name"] == "v2"
    assert b["created_at"] == a["created_at"]


@pytest.mark.asyncio
async def test_list_for_widget_filters(tmp_db_path):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    await store.upsert({"widget_id": "aqi", "name": "a1"})
    await store.upsert({"widget_id": "aqi", "name": "a2"})
    await store.upsert({"widget_id": "border", "name": "b1"})
    assert len(await store.list_for_widget("aqi")) == 2
    assert len(await store.list_for_widget("border")) == 1
    assert len(await store.list_for_widget("missing")) == 0


@pytest.mark.asyncio
async def test_delete(tmp_db_path):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    a = await store.upsert({"widget_id": "aqi", "name": "x"})
    await store.delete(a["id"])
    assert await store.get(a["id"]) is None


@pytest.mark.asyncio
async def test_evaluate_and_fire_edge_triggers(tmp_db_path, monkeypatch):
    """The rule fires once on false→true, not again while still true."""
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    await store.upsert({
        "widget_id": "aqi",
        "name": "test",
        "condition": {"path": "v", "op": ">", "value": 100},
        "message": "v is {v}",
        "actions": [{"type": "log"}],
        "cooldown_minutes": 0,
        "enabled": True,
    })

    fires = []
    async def fake_dispatch_all(actions, default_text=""):
        fires.append(default_text)
        return [{"ok": True, "detail": "ok", "channel": "log"}]
    monkeypatch.setattr(_n, "dispatch_all", fake_dispatch_all)

    # Below threshold — no fire
    await S.evaluate_and_fire(store, "aqi", {"v": 50})
    assert fires == []

    # Above threshold — fires once
    await S.evaluate_and_fire(store, "aqi", {"v": 150})
    assert fires == ["v is 150"]

    # Still above threshold — no re-fire (edge already fired)
    await S.evaluate_and_fire(store, "aqi", {"v": 200})
    assert fires == ["v is 150"]

    # Drop below — re-arm
    await S.evaluate_and_fire(store, "aqi", {"v": 50})
    # Rises again — fires
    await S.evaluate_and_fire(store, "aqi", {"v": 150})
    assert fires == ["v is 150", "v is 150"]


@pytest.mark.asyncio
async def test_evaluate_and_fire_respects_cooldown(tmp_db_path, monkeypatch):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    await store.upsert({
        "widget_id": "aqi",
        "name": "cooled",
        "condition": {"path": "v", "op": ">", "value": 0},
        "actions": [{"type": "log"}],
        "cooldown_minutes": 1,   # 60 seconds
    })

    fires = 0
    async def fake_dispatch_all(actions, default_text=""):
        nonlocal fires
        fires += 1
        return []
    monkeypatch.setattr(_n, "dispatch_all", fake_dispatch_all)

    # First fire
    await S.evaluate_and_fire(store, "aqi", {"v": 5})
    # Drop below, re-arm
    await S.evaluate_and_fire(store, "aqi", {"v": -1})
    # Rise again immediately — cooldown should block
    await S.evaluate_and_fire(store, "aqi", {"v": 5})
    assert fires == 1


@pytest.mark.asyncio
async def test_evaluate_and_fire_disabled_rules_skip(tmp_db_path, monkeypatch):
    store = S.SubscriptionStore(tmp_db_path)
    await store.init()
    await store.upsert({
        "widget_id": "aqi",
        "name": "off",
        "condition": {"path": "v", "op": ">", "value": 0},
        "actions": [{"type": "log"}],
        "enabled": False,
    })
    called = 0
    async def fake_dispatch_all(*a, **k):
        nonlocal called; called += 1
        return []
    monkeypatch.setattr(_n, "dispatch_all", fake_dispatch_all)
    await S.evaluate_and_fire(store, "aqi", {"v": 5})
    assert called == 0
