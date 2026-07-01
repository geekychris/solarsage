"""News archive: upsert dedup, recent ordering, translation join."""

from __future__ import annotations

import pytest

from app.news_store import NewsStore
from app.translations import TranslationsStore


@pytest.mark.asyncio
async def test_upsert_dedup_by_link(tmp_db_path):
    store = NewsStore(tmp_db_path)
    await store.init()
    items = [
        {"title": "First",  "link": "https://a/1", "published": ""},
        {"title": "Second", "link": "https://a/2", "published": ""},
    ]
    await store.upsert_items("test", "https://a/feed", "Test", items)
    rows = await store.recent("test", limit=10)
    assert {r["title"] for r in rows} == {"First", "Second"}

    # Second upsert with same links bumps last_seen_at, no dupes
    await store.upsert_items("test", "https://a/feed", "Test", items)
    rows2 = await store.recent("test", limit=10)
    assert len(rows2) == 2


@pytest.mark.asyncio
async def test_upsert_dedup_by_title_when_no_link(tmp_db_path):
    store = NewsStore(tmp_db_path)
    await store.init()
    await store.upsert_items("t", "url", "T", [{"title": "Foo", "link": ""}])
    await store.upsert_items("t", "url", "T", [{"title": "Foo", "link": ""}])
    assert len(await store.recent("t")) == 1


@pytest.mark.asyncio
async def test_recent_ordering(tmp_db_path):
    store = NewsStore(tmp_db_path)
    await store.init()
    await store.upsert_items("t", "url", "T", [
        {"title": "old", "link": "https://a/old"},
    ])
    # Small pause so last_seen_at differs. On very fast machines the
    # timestamps might tie, but sqlite ORDER BY DESC will still yield
    # deterministic-enough results within a test.
    import asyncio; await asyncio.sleep(0.01)
    await store.upsert_items("t", "url", "T", [
        {"title": "new", "link": "https://a/new"},
    ])
    rows = await store.recent("t", limit=10)
    assert rows[0]["title"] == "new"
    assert rows[1]["title"] == "old"


@pytest.mark.asyncio
async def test_recent_joins_translations(tmp_db_path):
    news = NewsStore(tmp_db_path)
    translations = TranslationsStore(tmp_db_path)
    await news.init()
    await translations.init()

    await news.upsert_items("t", "url", "T", [
        {"title": "hola mundo", "link": "https://a/1"},
        {"title": "adios",       "link": "https://a/2"},
    ])
    # Cache one translation
    await translations.add("es", "en", "hola mundo", "hello world")

    # Read without translation → all null
    plain = await news.recent("t")
    assert all(r["translated_title"] is None for r in plain)

    # Read with translation → the cached one populates, the other is null
    joined = await news.recent("t", translate_target="en", translate_source="es")
    by_title = {r["title"]: r for r in joined}
    assert by_title["hola mundo"]["translated_title"] == "hello world"
    assert by_title["adios"]["translated_title"] is None


@pytest.mark.asyncio
async def test_prune_older_than(tmp_db_path):
    store = NewsStore(tmp_db_path)
    await store.init()
    await store.upsert_items("t", "url", "T", [{"title": "x", "link": "https://x"}])
    # Very-far-back cutoff keeps everything (nothing is older than that)
    dropped = await store.prune_older_than(10 * 365 * 86400)  # 10 years
    assert dropped == 0
    # Cutoff of 0 seconds drops anything older than "now", which every
    # row in the store is (they were written slightly before this call).
    import time; time.sleep(0.02)
    dropped = await store.prune_older_than(0)
    assert dropped == 1
