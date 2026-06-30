"""SQLite-backed knowledge store for widget state + per-widget config."""

from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite

from .base import WidgetState


# The widget store shares the EG4 history DB with the high-frequency poller
# and the alerts watcher, so contention is real. WAL lets concurrent readers
# run while a single writer is active; busy_timeout makes writers queue
# briefly instead of giving up with "database is locked".
#
# WAL is persisted in the DB file header so a single PRAGMA at init time
# flips the whole database. busy_timeout is per-connection — apply it on
# every connect so writes from this module always wait their turn.
async def _connect(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA busy_timeout=5000")
    return db


class WidgetStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS widget_state (
                    widget_id   TEXT PRIMARY KEY,
                    fetched_at  REAL,
                    data_json   TEXT,
                    error       TEXT
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS widget_config (
                    widget_id   TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL
                )
                """
            )
            await db.commit()
        finally:
            await db.close()

    async def get_state(self, widget_id: str) -> WidgetState | None:
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT fetched_at, data_json, error FROM widget_state WHERE widget_id=?",
                (widget_id,),
            )
            row = await cur.fetchone()
        finally:
            await db.close()
        if not row:
            return None
        fetched_at, data_json, error = row
        return WidgetState(
            fetched_at=fetched_at,
            data=json.loads(data_json) if data_json else None,
            error=error,
        )

    async def put_state(self, widget_id: str, state: WidgetState) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                """
                INSERT INTO widget_state(widget_id, fetched_at, data_json, error)
                VALUES (?,?,?,?)
                ON CONFLICT(widget_id) DO UPDATE SET
                    fetched_at=excluded.fetched_at,
                    data_json =excluded.data_json,
                    error     =excluded.error
                """,
                (
                    widget_id,
                    state.fetched_at,
                    json.dumps(state.data) if state.data is not None else None,
                    state.error,
                ),
            )
            await db.commit()
        finally:
            await db.close()

    async def record_error(self, widget_id: str, error: str) -> None:
        prev = await self.get_state(widget_id)
        # Keep the last good data on a transient failure — the UI can show
        # "stale since X" rather than an empty card.
        data = prev.data if prev else None
        await self.put_state(
            widget_id,
            WidgetState(fetched_at=time.time(), data=data, error=error),
        )

    async def record_success(self, widget_id: str, data: Any) -> None:
        await self.put_state(
            widget_id,
            WidgetState(fetched_at=time.time(), data=data, error=None),
        )

    async def get_config(self, widget_id: str) -> dict[str, Any] | None:
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT config_json FROM widget_config WHERE widget_id=?",
                (widget_id,),
            )
            row = await cur.fetchone()
        finally:
            await db.close()
        if not row:
            return None
        return json.loads(row[0])

    async def put_config(self, widget_id: str, config: dict[str, Any]) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                """
                INSERT INTO widget_config(widget_id, config_json)
                VALUES (?,?)
                ON CONFLICT(widget_id) DO UPDATE SET config_json=excluded.config_json
                """,
                (widget_id, json.dumps(config)),
            )
            await db.commit()
        finally:
            await db.close()
