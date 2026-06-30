"""SQLite store for events + their reminder rules.

Schema:
    events(id, source, source_ref, title, starts_at, ends_at, notes,
           is_special, snoozed, user_edited, created_at, updated_at)
    reminders(id, event_id, minutes_before, mode, custom_text, fired_at)

``user_edited=1`` marks an event that the user has tweaked through PUT
/api/events/{id}; the HOA ingest then skips overwriting its title/time
so manual edits aren't clobbered on the next refresh.
"""

from __future__ import annotations

import json
import time as _time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiosqlite


async def _connect(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA busy_timeout=5000")
    return db


@dataclass
class Reminder:
    id: str
    event_id: str
    minutes_before: int
    mode: str = "tts"
    custom_text: str | None = None
    fired_at: float | None = None


@dataclass
class Event:
    id: str
    source: str            # "hoa" | "manual"
    source_ref: str | None
    title: str
    starts_at: str         # ISO-8601 in UTC
    ends_at: str | None = None
    notes: str | None = None
    is_special: bool = True
    snoozed: bool = False
    user_edited: bool = False
    created_at: float = field(default_factory=_time.time)
    updated_at: float = field(default_factory=_time.time)
    reminders: list[Reminder] = field(default_factory=list)


def _row_to_event(row: tuple, reminders: list[Reminder]) -> Event:
    (
        eid, source, source_ref, title, starts_at, ends_at, notes,
        is_special, snoozed, user_edited, created_at, updated_at,
    ) = row
    return Event(
        id=eid, source=source, source_ref=source_ref, title=title,
        starts_at=starts_at, ends_at=ends_at, notes=notes,
        is_special=bool(is_special), snoozed=bool(snoozed),
        user_edited=bool(user_edited), created_at=created_at,
        updated_at=updated_at, reminders=reminders,
    )


class EventStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id           TEXT PRIMARY KEY,
                    source       TEXT NOT NULL,
                    source_ref   TEXT,
                    title        TEXT NOT NULL,
                    starts_at    TEXT NOT NULL,
                    ends_at      TEXT,
                    notes        TEXT,
                    is_special   INTEGER NOT NULL DEFAULT 1,
                    snoozed      INTEGER NOT NULL DEFAULT 0,
                    user_edited  INTEGER NOT NULL DEFAULT 0,
                    created_at   REAL NOT NULL,
                    updated_at   REAL NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_source_ref
                    ON events(source_ref) WHERE source_ref IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_events_starts_at
                    ON events(starts_at);

                CREATE TABLE IF NOT EXISTS reminders (
                    id              TEXT PRIMARY KEY,
                    event_id        TEXT NOT NULL REFERENCES events(id)
                                       ON DELETE CASCADE,
                    minutes_before  INTEGER NOT NULL,
                    mode            TEXT NOT NULL DEFAULT 'tts',
                    custom_text     TEXT,
                    fired_at        REAL
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_event_id
                    ON reminders(event_id);
                """
            )
            await db.commit()
        finally:
            await db.close()

    async def list_events(
        self,
        *,
        starts_after: str | None = None,
        starts_before: str | None = None,
    ) -> list[Event]:
        db = await _connect(self.db_path)
        try:
            sql = (
                "SELECT id, source, source_ref, title, starts_at, ends_at, "
                "notes, is_special, snoozed, user_edited, created_at, "
                "updated_at FROM events"
            )
            args: list[Any] = []
            where = []
            if starts_after:
                where.append("starts_at >= ?")
                args.append(starts_after)
            if starts_before:
                where.append("starts_at < ?")
                args.append(starts_before)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY starts_at"
            cur = await db.execute(sql, args)
            rows = await cur.fetchall()
            results: list[Event] = []
            for row in rows:
                eid = row[0]
                rcur = await db.execute(
                    "SELECT id, event_id, minutes_before, mode, custom_text, "
                    "fired_at FROM reminders WHERE event_id=? "
                    "ORDER BY minutes_before DESC",
                    (eid,),
                )
                rs = [
                    Reminder(
                        id=r[0], event_id=r[1], minutes_before=r[2],
                        mode=r[3], custom_text=r[4], fired_at=r[5],
                    )
                    for r in await rcur.fetchall()
                ]
                results.append(_row_to_event(row, rs))
        finally:
            await db.close()
        return results

    async def get(self, event_id: str) -> Event | None:
        events = await self.list_events()
        for e in events:
            if e.id == event_id:
                return e
        return None

    async def upsert_hoa(self, ev: Event) -> Event:
        """Idempotent ingest: insert by source_ref, but never overwrite a
        user-edited row. Reminders are seeded once on first insert; later
        ingests leave them alone."""
        if not ev.source_ref:
            raise ValueError("hoa event must have source_ref")
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT id, user_edited FROM events WHERE source_ref=?",
                (ev.source_ref,),
            )
            row = await cur.fetchone()
            if row is None:
                ev.id = ev.id or str(uuid.uuid4())
                await db.execute(
                    """
                    INSERT INTO events(id, source, source_ref, title,
                        starts_at, ends_at, notes, is_special, snoozed,
                        user_edited, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ev.id, ev.source, ev.source_ref, ev.title,
                        ev.starts_at, ev.ends_at, ev.notes,
                        int(ev.is_special), int(ev.snoozed),
                        int(ev.user_edited), ev.created_at, ev.updated_at,
                    ),
                )
                for r in ev.reminders:
                    r.id = r.id or str(uuid.uuid4())
                    r.event_id = ev.id
                    await db.execute(
                        "INSERT INTO reminders(id, event_id, "
                        "minutes_before, mode, custom_text, fired_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (r.id, r.event_id, r.minutes_before, r.mode,
                         r.custom_text, r.fired_at),
                    )
                await db.commit()
                ev.id = ev.id
                return ev
            existing_id, user_edited = row
            ev.id = existing_id
            if not user_edited:
                # Only refresh time/title/special if the user hasn't
                # taken ownership of the row.
                await db.execute(
                    """
                    UPDATE events SET title=?, starts_at=?, ends_at=?,
                        is_special=?, updated_at=? WHERE id=?
                    """,
                    (
                        ev.title, ev.starts_at, ev.ends_at,
                        int(ev.is_special), _time.time(), existing_id,
                    ),
                )
                await db.commit()
            return ev
        finally:
            await db.close()

    async def insert_manual(self, ev: Event) -> Event:
        ev.id = ev.id or str(uuid.uuid4())
        ev.source = "manual"
        db = await _connect(self.db_path)
        try:
            await db.execute(
                """
                INSERT INTO events(id, source, source_ref, title, starts_at,
                    ends_at, notes, is_special, snoozed, user_edited,
                    created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ev.id, ev.source, ev.source_ref, ev.title, ev.starts_at,
                    ev.ends_at, ev.notes, int(ev.is_special),
                    int(ev.snoozed), int(True), ev.created_at, ev.updated_at,
                ),
            )
            for r in ev.reminders:
                r.id = r.id or str(uuid.uuid4())
                r.event_id = ev.id
                await db.execute(
                    "INSERT INTO reminders(id, event_id, minutes_before, "
                    "mode, custom_text, fired_at) VALUES (?,?,?,?,?,?)",
                    (r.id, r.event_id, r.minutes_before, r.mode,
                     r.custom_text, r.fired_at),
                )
            await db.commit()
        finally:
            await db.close()
        return ev

    async def update(
        self, event_id: str, *, title: str | None = None,
        starts_at: str | None = None, ends_at: str | None = None,
        notes: str | None = None, is_special: bool | None = None,
        snoozed: bool | None = None,
    ) -> None:
        sets: list[str] = []
        args: list[Any] = []
        for col, val in (
            ("title", title), ("starts_at", starts_at), ("ends_at", ends_at),
            ("notes", notes),
            ("is_special", None if is_special is None else int(is_special)),
            ("snoozed", None if snoozed is None else int(snoozed)),
        ):
            if val is not None:
                sets.append(f"{col}=?")
                args.append(val)
        if not sets:
            return
        sets.append("user_edited=1")
        sets.append("updated_at=?")
        args.append(_time.time())
        args.append(event_id)
        db = await _connect(self.db_path)
        try:
            await db.execute(
                f"UPDATE events SET {', '.join(sets)} WHERE id=?", args
            )
            await db.commit()
        finally:
            await db.close()

    async def delete(self, event_id: str) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute("DELETE FROM events WHERE id=?", (event_id,))
            await db.commit()
        finally:
            await db.close()

    async def set_reminders(
        self, event_id: str, reminders: list[Reminder],
    ) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                "DELETE FROM reminders WHERE event_id=?", (event_id,)
            )
            for r in reminders:
                r.id = r.id or str(uuid.uuid4())
                r.event_id = event_id
                await db.execute(
                    "INSERT INTO reminders(id, event_id, minutes_before, "
                    "mode, custom_text, fired_at) VALUES (?,?,?,?,?,?)",
                    (r.id, r.event_id, r.minutes_before, r.mode,
                     r.custom_text, r.fired_at),
                )
            await db.execute(
                "UPDATE events SET user_edited=1, updated_at=? WHERE id=?",
                (_time.time(), event_id),
            )
            await db.commit()
        finally:
            await db.close()

    async def mark_fired(self, reminder_id: str, ts: float) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                "UPDATE reminders SET fired_at=? WHERE id=?",
                (ts, reminder_id),
            )
            await db.commit()
        finally:
            await db.close()

    async def prune_past(self, before_iso: str) -> int:
        """Drop events whose ``starts_at`` < before_iso."""
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "DELETE FROM events WHERE starts_at < ?", (before_iso,)
            )
            await db.commit()
            return cur.rowcount or 0
        finally:
            await db.close()


def event_to_dict(ev: Event) -> dict[str, Any]:
    d = asdict(ev)
    return d
