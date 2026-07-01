"""Threshold subscriptions — rules that fire notification actions when
a widget's data crosses a condition (false → true edge).

Rule shape (stored as JSON in the ``subscriptions`` table):

    {
        "id": "…",
        "name": "AQI unhealthy",
        "widget_id": "aqi",
        "condition": {
            "path": "current.us_aqi",   # dotted path into widget data
            "op": ">",                  # >, >=, <, <=, ==, !=, contains, changed
            "value": 100
        },
        "message": "AQI is {current.us_aqi} ({current.category})",
        "actions": [
            {"type": "tts"},
            {"type": "telegram", "title": "Air quality alert"}
        ],
        "enabled": true,
        "cooldown_minutes": 60,   # don't re-fire within this window
        "last_state": false,      # last-evaluated boolean (for edge detection)
        "last_fired_at": null     # epoch seconds
    }

The evaluator runs after every widget refresh; it walks each rule for
that widget, evaluates the condition against the fresh data, and — if
the condition transitioned from false → true (or ``op == "changed"``
returned true) — fires the actions via ``notify.dispatch_all``.
"""

from __future__ import annotations

import json
import logging
import re
import time as _time
import uuid
from typing import Any

import aiosqlite

from . import notify

log = logging.getLogger("eg4.subs")


async def _connect(db_path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA busy_timeout=5000")
    return db


class SubscriptionStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id             TEXT PRIMARY KEY,
                    widget_id      TEXT NOT NULL,
                    rule_json      TEXT NOT NULL,
                    last_state     INTEGER NOT NULL DEFAULT 0,
                    last_fired_at  REAL,
                    last_result    TEXT,
                    created_at     REAL NOT NULL,
                    updated_at     REAL NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_subs_widget ON subscriptions(widget_id)"
            )
            await db.commit()
        finally:
            await db.close()

    async def list_all(self) -> list[dict[str, Any]]:
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT id, widget_id, rule_json, last_state, "
                "last_fired_at, last_result, created_at, updated_at "
                "FROM subscriptions ORDER BY created_at"
            )
            rows = await cur.fetchall()
        finally:
            await db.close()
        return [_row_to_dict(r) for r in rows]

    async def list_for_widget(self, widget_id: str) -> list[dict[str, Any]]:
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT id, widget_id, rule_json, last_state, "
                "last_fired_at, last_result, created_at, updated_at "
                "FROM subscriptions WHERE widget_id=? ORDER BY created_at",
                (widget_id,),
            )
            rows = await cur.fetchall()
        finally:
            await db.close()
        return [_row_to_dict(r) for r in rows]

    async def get(self, sub_id: str) -> dict[str, Any] | None:
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT id, widget_id, rule_json, last_state, "
                "last_fired_at, last_result, created_at, updated_at "
                "FROM subscriptions WHERE id=?",
                (sub_id,),
            )
            row = await cur.fetchone()
        finally:
            await db.close()
        return _row_to_dict(row) if row else None

    async def upsert(self, sub: dict[str, Any]) -> dict[str, Any]:
        sub = dict(sub)
        sub.setdefault("id", str(uuid.uuid4()))
        widget_id = sub.get("widget_id")
        if not widget_id:
            raise ValueError("widget_id required")
        rule_json = json.dumps({
            k: v for k, v in sub.items()
            if k not in ("id", "widget_id", "last_state", "last_fired_at",
                         "last_result", "created_at", "updated_at")
        })
        now = _time.time()
        db = await _connect(self.db_path)
        try:
            cur = await db.execute(
                "SELECT id, created_at FROM subscriptions WHERE id=?",
                (sub["id"],),
            )
            existing = await cur.fetchone()
            if existing:
                await db.execute(
                    "UPDATE subscriptions SET widget_id=?, rule_json=?, "
                    "updated_at=? WHERE id=?",
                    (widget_id, rule_json, now, sub["id"]),
                )
                created_at = existing[1]
            else:
                await db.execute(
                    "INSERT INTO subscriptions(id, widget_id, rule_json, "
                    "created_at, updated_at) VALUES (?,?,?,?,?)",
                    (sub["id"], widget_id, rule_json, now, now),
                )
                created_at = now
            await db.commit()
        finally:
            await db.close()
        return await self.get(sub["id"])

    async def delete(self, sub_id: str) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute("DELETE FROM subscriptions WHERE id=?", (sub_id,))
            await db.commit()
        finally:
            await db.close()

    async def record_fire(
        self, sub_id: str, new_state: bool, result_summary: str,
    ) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                "UPDATE subscriptions SET last_state=?, last_fired_at=?, "
                "last_result=? WHERE id=?",
                (int(new_state), _time.time(), result_summary[:400], sub_id),
            )
            await db.commit()
        finally:
            await db.close()

    async def record_state(self, sub_id: str, new_state: bool) -> None:
        db = await _connect(self.db_path)
        try:
            await db.execute(
                "UPDATE subscriptions SET last_state=? WHERE id=?",
                (int(new_state), sub_id),
            )
            await db.commit()
        finally:
            await db.close()


# --- Condition evaluation ----------------------------------------------

def _get_by_path(obj: Any, path: str) -> Any:
    """dotted-path lookup with support for [n] indices.
    e.g. ``ports[0].pov.standard.delay_minutes``"""
    if not path:
        return obj
    cur = obj
    for part in re.split(r"\.(?![^\[]*\])", path):
        # split index parts
        m = re.match(r"^([^\[]+)((?:\[\d+\])*)$", part)
        if not m:
            return None
        key = m.group(1)
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
        for idx_match in re.finditer(r"\[(\d+)\]", m.group(2)):
            i = int(idx_match.group(1))
            if isinstance(cur, list) and 0 <= i < len(cur):
                cur = cur[i]
            else:
                return None
        if cur is None:
            return None
    return cur


def _cmp(actual: Any, op: str, expected: Any) -> bool:
    if op == "changed":
        # "changed" is edge-detection on the value itself; caller
        # compares actual against previous. Here we just return True
        # when actual is not None.
        return actual is not None
    if actual is None:
        return False
    try:
        if op == "==":  return actual == expected
        if op == "!=":  return actual != expected
        if op == ">":   return float(actual) >  float(expected)
        if op == ">=":  return float(actual) >= float(expected)
        if op == "<":   return float(actual) <  float(expected)
        if op == "<=":  return float(actual) <= float(expected)
        if op == "contains":
            return str(expected).lower() in str(actual).lower()
        if op == "not_contains":
            return str(expected).lower() not in str(actual).lower()
    except (TypeError, ValueError):
        return False
    return False


def evaluate_condition(data: Any, condition: dict[str, Any]) -> tuple[bool, Any]:
    """Return ``(matched, actual_value)`` for the condition against
    the widget's data payload."""
    path = str(condition.get("path") or "")
    op = str(condition.get("op") or "==")
    expected = condition.get("value")
    actual = _get_by_path(data, path)
    return _cmp(actual, op, expected), actual


def render_message(template: str, data: Any) -> str:
    """Very small template — replaces ``{a.b.c}`` with the path lookup
    into ``data``. Missing paths render as empty string."""
    if not template:
        return ""
    def _sub(match: re.Match) -> str:
        v = _get_by_path(data, match.group(1))
        return "" if v is None else str(v)
    return re.sub(r"\{([^{}]+)\}", _sub, template)


# --- Firing --------------------------------------------------------------

async def evaluate_and_fire(
    store: "SubscriptionStore",
    widget_id: str,
    widget_data: Any,
) -> list[dict[str, Any]]:
    """Called after every widget refresh. Walk each rule for this
    widget, edge-detect condition transitions, fire when new."""
    subs = await store.list_for_widget(widget_id)
    fired = []
    for sub in subs:
        rule = sub.get("rule") or {}
        if not rule.get("enabled", True):
            continue
        cond = rule.get("condition") or {}
        cooldown = float(rule.get("cooldown_minutes", 0)) * 60
        try:
            matched, actual = evaluate_condition(widget_data, cond)
        except Exception as exc:  # noqa: BLE001
            log.warning("sub %s eval failed: %s", sub["id"], exc)
            continue
        prev = bool(sub.get("last_state"))
        # Edge trigger: fire when the condition transitions false → true
        # ('changed' op always fires on any non-None value; treat every
        # tick as a new state).
        if cond.get("op") == "changed":
            # For "changed", compare actual to last_fired value in
            # sub['rule']['_last_seen'] — simplification: fire every
            # tick where it's non-None but obey cooldown.
            should_fire = actual is not None
        else:
            should_fire = matched and not prev
        if not should_fire:
            # Update stored state even if not firing so we can detect
            # the next false→true edge cleanly.
            if matched != prev:
                await store.record_state(sub["id"], matched)
            continue
        # Cooldown
        now = _time.time()
        last = sub.get("last_fired_at") or 0.0
        if cooldown and now - last < cooldown:
            log.info(
                "sub %s (%s) matched but within cooldown (%.0fs remaining)",
                sub["id"], rule.get("name"), cooldown - (now - last),
            )
            await store.record_state(sub["id"], matched)
            continue
        # Render message + fire actions
        template = rule.get("message") or f"{widget_id}: {rule.get('name')}"
        message = render_message(template, widget_data)
        actions = rule.get("actions") or []
        results = await notify.dispatch_all(actions, default_text=message)
        summary = "; ".join(
            f"{r['channel']}:{'ok' if r['ok'] else r['detail'][:80]}"
            for r in results
        )
        await store.record_fire(sub["id"], matched, summary)
        fired.append({
            "id": sub["id"],
            "name": rule.get("name"),
            "widget_id": widget_id,
            "message": message,
            "results": results,
        })
    return fired


def _row_to_dict(row: tuple | None) -> dict[str, Any] | None:
    if not row:
        return None
    (sid, wid, rule_json, last_state, last_fired_at, last_result,
     created_at, updated_at) = row
    rule = json.loads(rule_json) if rule_json else {}
    return {
        "id": sid,
        "widget_id": wid,
        "rule": rule,
        "last_state": bool(last_state),
        "last_fired_at": last_fired_at,
        "last_result": last_result,
        "created_at": created_at,
        "updated_at": updated_at,
    }
