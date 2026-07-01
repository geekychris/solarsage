"""Translations store: add, lookup, cache semantics.

We stub out MyMemory since these tests should be offline."""

from __future__ import annotations

import pytest

from app import translations as _t


@pytest.mark.asyncio
async def test_add_and_recent(tmp_db_path):
    store = _t.TranslationsStore(tmp_db_path)
    await store.init()
    tid = await store.add("en", "es", "hello", "hola")
    assert isinstance(tid, int) and tid > 0
    recent = await store.recent(limit=10)
    assert len(recent) == 1
    r = recent[0]
    assert r["source_text"] == "hello"
    assert r["target_text"] == "hola"
    assert r["starred"] is False


@pytest.mark.asyncio
async def test_find_hit_and_miss(tmp_db_path):
    store = _t.TranslationsStore(tmp_db_path)
    await store.init()
    assert await store.find("en", "es", "hello") is None
    await store.add("en", "es", "hello", "hola")
    assert await store.find("en", "es", "hello") == "hola"
    # Case-sensitive
    assert await store.find("en", "es", "Hello") is None
    # Wrong direction misses
    assert await store.find("es", "en", "hello") is None


@pytest.mark.asyncio
async def test_translate_cached_hits_cache(tmp_db_path, monkeypatch):
    store = _t.TranslationsStore(tmp_db_path)
    await store.init()

    calls: list[str] = []

    async def fake_mm(text, source="en", target="es"):
        calls.append(text)
        return f"{text} [{source}->{target}]"

    monkeypatch.setattr(_t, "mymemory_translate", fake_mm)

    # First call → MyMemory
    r1 = await store.translate_cached("en", "es", "hello")
    assert r1 == "hello [en->es]"
    assert len(calls) == 1
    # Second call → cache hit, no MyMemory call
    r2 = await store.translate_cached("en", "es", "hello")
    assert r2 == "hello [en->es]"
    assert len(calls) == 1
    # Different target → miss
    await store.translate_cached("en", "fr", "hello")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_star_and_delete(tmp_db_path):
    store = _t.TranslationsStore(tmp_db_path)
    await store.init()
    tid = await store.add("en", "es", "hello", "hola")
    await store.toggle_star(tid)
    assert (await store.recent())[0]["starred"] is True
    await store.toggle_star(tid)
    assert (await store.recent())[0]["starred"] is False
    await store.delete(tid)
    assert await store.recent() == []
