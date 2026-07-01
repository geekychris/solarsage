"""Persistent archive of news items pulled from RSS/Atom feeds.

Every fetch of the news / baja_news widget upserts its items here so
we accumulate a searchable history — you can look up "when did that
story first appear" long after it dropped off the live feed.

Each row is keyed by ``(widget_id, dedup_key)`` where dedup_key is the
``link`` when present and the ``title`` otherwise. Re-fetching an item
just bumps ``last_seen_at``.

Translations are NOT stored here — the ``translations`` table already
serves as the cache. ``recent()`` joins on it (``source_text = title``)
so viewers see any cached translation immediately without extra
lookups.
"""

from __future__ import annotations

import time as _time
from typing import Any

import aiosqlite


async def _connect(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA busy_timeout=5000")
    return db


class NewsStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        db = await _connect(self.db_path)
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS news_items (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    widget_id      TEXT NOT NULL,
                    feed_url       TEXT NOT NULL,
                    feed_label     TEXT,
                    dedup_key      TEXT NOT NULL,
                    title          TEXT NOT NULL,
                    link           TEXT,
                    published      TEXT,
                    summary        TEXT,
                    first_seen_at  REAL NOT NULL,
                    last_seen_at   REAL NOT NULL,
                    UNIQUE(widget_id, dedup_key)
                );
                CREATE INDEX IF NOT EXISTS idx_news_widget_last
                    ON news_items(widget_id, last_seen_at DESC);
                CREATE INDEX IF NOT EXISTS idx_news_widget_first
                    ON news_items(widget_id, first_seen_at DESC);
                """
            )
            await db.commit()
        finally:
            await db.close()

    async def upsert_items(
        self,
        widget_id: str,
        feed_url: str,
        feed_label: str | None,
        items: list[dict[str, Any]],
    ) -> None:
        if not items:
            return
        now = _time.time()
        db = await _connect(self.db_path)
        try:
            for it in items:
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                link = (it.get("link") or "").strip() or None
                dedup_key = link or title
                await db.execute(
                    """
                    INSERT INTO news_items(
                        widget_id, feed_url, feed_label, dedup_key,
                        title, link, published, summary,
                        first_seen_at, last_seen_at
                    )
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(widget_id, dedup_key) DO UPDATE SET
                        feed_label = excluded.feed_label,
                        published  = COALESCE(NULLIF(excluded.published, ''), published),
                        summary    = COALESCE(NULLIF(excluded.summary, ''), summary),
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        widget_id, feed_url, feed_label or "", dedup_key,
                        title, link, it.get("published") or "",
                        it.get("summary") or "",
                        now, now,
                    ),
                )
            await db.commit()
        finally:
            await db.close()

    async def recent(
        self,
        widget_id: str,
        *,
        translate_target: str | None = None,
        translate_source: str = "es",
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """Return most-recently-seen items for a widget. If
        ``translate_target`` is set, LEFT JOIN against the translations
        table so each item carries its cached English (or whatever) title
        when available."""
        db = await _connect(self.db_path)
        try:
            if translate_target:
                sql = (
                    "SELECT n.id, n.widget_id, n.feed_url, n.feed_label, "
                    "n.title, n.link, n.published, n.summary, "
                    "n.first_seen_at, n.last_seen_at, "
                    "t.target_text AS translated_title "
                    "FROM news_items n "
                    "LEFT JOIN translations t "
                    "  ON t.source = ? AND t.target = ? "
                    "  AND t.source_text = n.title "
                    "WHERE n.widget_id = ? "
                    "ORDER BY n.last_seen_at DESC LIMIT ?"
                )
                args = (translate_source, translate_target, widget_id, limit)
            else:
                sql = (
                    "SELECT id, widget_id, feed_url, feed_label, "
                    "title, link, published, summary, "
                    "first_seen_at, last_seen_at, NULL AS translated_title "
                    "FROM news_items WHERE widget_id = ? "
                    "ORDER BY last_seen_at DESC LIMIT ?"
                )
                args = (widget_id, limit)
            cur = await db.execute(sql, args)
            rows = await cur.fetchall()
        finally:
            await db.close()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r[0],
                "widget_id": r[1],
                "feed_url": r[2],
                "feed_label": r[3],
                "title": r[4],
                "link": r[5],
                "published": r[6],
                "summary": r[7],
                "first_seen_at": r[8],
                "last_seen_at": r[9],
                "translated_title": r[10],
            })
        return out

    async def get(self, item_id: int) -> dict[str, Any] | None:
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT id, widget_id, feed_url, feed_label, title, link, "
                "published, summary, first_seen_at, last_seen_at "
                "FROM news_items WHERE id = ?",
                (item_id,),
            )
            r = await cur.fetchone()
        finally:
            await db.close()
        if not r:
            return None
        return {
            "id": r[0], "widget_id": r[1], "feed_url": r[2],
            "feed_label": r[3], "title": r[4], "link": r[5],
            "published": r[6], "summary": r[7],
            "first_seen_at": r[8], "last_seen_at": r[9],
        }

    async def prune_older_than(self, seconds: int) -> int:
        cutoff = _time.time() - seconds
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "DELETE FROM news_items WHERE last_seen_at < ?",
                (cutoff,),
            )
            await db.commit()
            return cur.rowcount or 0
        finally:
            await db.close()
