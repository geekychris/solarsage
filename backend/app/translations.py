"""Translations store + MyMemory client.

Persists every translation the user asks for so the Spanish widget can
show a rolling history. MyMemory is free and doesn't require a key
below 5,000 words/day per anonymous IP.
"""

from __future__ import annotations

import time
from typing import Any

import aiohttp
import aiosqlite


MYMEMORY_URL = "https://api.mymemory.translated.net/get"


class TranslationsStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self.db_path)
        await db.execute("PRAGMA busy_timeout=5000")
        return db

    async def init(self) -> None:
        db = await self._connect()
        try:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts           REAL NOT NULL,
                    source       TEXT NOT NULL,
                    target       TEXT NOT NULL,
                    source_text  TEXT NOT NULL,
                    target_text  TEXT NOT NULL,
                    starred      INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_translations_ts
                    ON translations(ts DESC);
                """
            )
            await db.commit()
        finally:
            await db.close()

    async def add(
        self,
        source: str,
        target: str,
        source_text: str,
        target_text: str,
    ) -> int:
        db = await self._connect()
        try:
            cur = await db.execute(
                "INSERT INTO translations(ts, source, target, source_text, "
                "target_text, starred) VALUES (?,?,?,?,?,0)",
                (time.time(), source, target, source_text, target_text),
            )
            await db.commit()
            return cur.lastrowid
        finally:
            await db.close()

    async def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        db = await self._connect()
        try:
            cur = await db.execute(
                "SELECT id, ts, source, target, source_text, target_text, "
                "starred FROM translations ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
        finally:
            await db.close()
        return [
            {
                "id": r[0], "ts": r[1], "source": r[2], "target": r[3],
                "source_text": r[4], "target_text": r[5],
                "starred": bool(r[6]),
            }
            for r in rows
        ]

    async def find(
        self, source: str, target: str, source_text: str,
    ) -> str | None:
        """Cache lookup: return the target text if we've translated this
        exact source text before, else None."""
        db = await self._connect()
        try:
            cur = await db.execute(
                "SELECT target_text FROM translations WHERE source=? "
                "AND target=? AND source_text=? "
                "ORDER BY ts DESC LIMIT 1",
                (source, target, source_text),
            )
            row = await cur.fetchone()
            return row[0] if row else None
        finally:
            await db.close()

    async def translate_cached(
        self, source: str, target: str, source_text: str,
    ) -> str:
        """Look up a translation in the cache, or call MyMemory + store.

        Errors from MyMemory propagate — the caller decides whether to
        keep the original text on failure.
        """
        hit = await self.find(source, target, source_text)
        if hit is not None:
            return hit
        translated = await mymemory_translate(
            source_text, source=source, target=target,
        )
        await self.add(source, target, source_text, translated)
        return translated

    async def toggle_star(self, translation_id: int) -> None:
        db = await self._connect()
        try:
            await db.execute(
                "UPDATE translations SET starred = 1 - starred WHERE id = ?",
                (translation_id,),
            )
            await db.commit()
        finally:
            await db.close()

    async def delete(self, translation_id: int) -> None:
        db = await self._connect()
        try:
            await db.execute("DELETE FROM translations WHERE id = ?", (translation_id,))
            await db.commit()
        finally:
            await db.close()


async def mymemory_translate(text: str, source: str = "en", target: str = "es") -> str:
    """Free public translation. Returns the translated string."""
    params = {"q": text, "langpair": f"{source}|{target}"}
    async with aiohttp.ClientSession() as http:
        async with http.get(
            MYMEMORY_URL, params=params, timeout=15,
            headers={"User-Agent": "SolarSage/1.0 (translations)"},
        ) as r:
            r.raise_for_status()
            payload = await r.json(content_type=None)
    resp = payload.get("responseData") or {}
    translated = (resp.get("translatedText") or "").strip()
    if not translated:
        raise RuntimeError(f"MyMemory returned no translation: {payload}")
    return translated
