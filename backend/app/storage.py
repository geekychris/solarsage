"""SQLite-backed time-series store for EG4 inverter snapshots.

Schema is tall/skinny (serial_num, ts, category, field, value) so we can add new
fields without migrations — the EG4 API returns dynamic dictionaries with dozens
of metrics, and we want all of them queryable.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  serial_num TEXT NOT NULL,
  ts INTEGER NOT NULL,
  category TEXT NOT NULL,
  field TEXT NOT NULL,
  value REAL NOT NULL,
  site_id TEXT NOT NULL DEFAULT 'site-1'
);
CREATE INDEX IF NOT EXISTS idx_samples_lookup
  ON samples(serial_num, field, ts);
CREATE INDEX IF NOT EXISTS idx_samples_recent
  ON samples(serial_num, ts);
-- idx_samples_site is created in MIGRATIONS, after we ensure the column exists
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sites (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  vendor TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  tz TEXT NOT NULL,
  peak_kw REAL NOT NULL DEFAULT 10.0,
  battery_capacity_kwh REAL NOT NULL DEFAULT 14.3,
  max_charge_kw REAL NOT NULL DEFAULT 8.0,
  config_json TEXT NOT NULL DEFAULT '{}',
  credentials_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS appliances (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL,
  name TEXT NOT NULL,
  watts REAL NOT NULL,
  typical_minutes INTEGER NOT NULL DEFAULT 60,
  can_defer INTEGER NOT NULL DEFAULT 1,
  preferred_start_hour INTEGER,
  preferred_end_hour INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_appliances_site ON appliances(site_id);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  severity TEXT NOT NULL,
  rule TEXT NOT NULL,
  message TEXT NOT NULL,
  acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_recent ON alerts(site_id, ts);
CREATE TABLE IF NOT EXISTS web_sessions (
  token TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS announcement_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  source TEXT NOT NULL,
  text TEXT NOT NULL,
  channels TEXT NOT NULL,
  ok INTEGER NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_announcement_history_recent
  ON announcement_history(ts DESC);
CREATE TABLE IF NOT EXISTS network_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  target TEXT NOT NULL,
  ok INTEGER NOT NULL,
  latency_ms INTEGER,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_network_checks_recent
  ON network_checks(ts DESC);
CREATE TABLE IF NOT EXISTS network_outages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_ts INTEGER NOT NULL,
  ended_ts INTEGER,
  duration_seconds INTEGER,
  notified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_network_outages_recent
  ON network_outages(started_ts DESC);
"""

# Run after CREATE TABLE — adds site_id to existing tables for users
# upgrading from a pre-multi-site DB. ALTER TABLE ADD COLUMN is idempotent-ish
# in SQLite (errors if the column exists), so we swallow that case.
MIGRATIONS = [
    "ALTER TABLE samples ADD COLUMN site_id TEXT NOT NULL DEFAULT 'site-1'",
    "CREATE INDEX IF NOT EXISTS idx_samples_site ON samples(site_id, field, ts)",
]


class History:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            for stmt in MIGRATIONS:
                try:
                    await db.execute(stmt)
                except Exception:
                    # column already exists; ignore
                    pass
            await db.commit()

    @staticmethod
    def _flatten(category: str, data: dict[str, Any]) -> list[tuple[str, float]]:
        """Return [(field, numeric_value)] for every scalar number in `data`.

        Skips strings, lists, dicts, None, and private/internal keys. The EG4
        responses mix numbers and labels — we keep only numbers for charting.
        """
        out: list[tuple[str, float]] = []
        for k, v in data.items():
            if k.startswith("_"):
                continue
            if isinstance(v, bool):
                # bools are ints in python but useless as time-series — skip
                continue
            if isinstance(v, (int, float)):
                out.append((k, float(v)))
        return out

    async def record(
        self,
        serial_num: str,
        category: str,
        data: dict[str, Any],
        ts_ms: int | None = None,
    ) -> int:
        ts = ts_ms if ts_ms is not None else int(time.time() * 1000)
        rows = [(serial_num, ts, category, f, v) for f, v in self._flatten(category, data)]
        if not rows:
            return 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT INTO samples (serial_num, ts, category, field, value)"
                " VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()
        return len(rows)

    async def upsert_many(
        self,
        serial_num: str,
        category: str,
        samples: list[tuple[int, dict[str, float]]],
    ) -> int:
        """Insert historical samples idempotently — backfill can be re-run safely.

        Idempotency key: (serial_num, ts, category, field). We delete the
        existing row for that key inside the same transaction, then insert.
        """
        if not samples:
            return 0
        rows: list[tuple[str, int, str, str, float]] = []
        for ts_ms, fields in samples:
            for f, v in fields.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    rows.append((serial_num, int(ts_ms), category, f, float(v)))
        if not rows:
            return 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN")
            await db.executemany(
                "DELETE FROM samples WHERE serial_num=? AND ts=? AND category=? AND field=?",
                [(r[0], r[1], r[2], r[3]) for r in rows],
            )
            await db.executemany(
                "INSERT INTO samples (serial_num, ts, category, field, value)"
                " VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()
        return len(rows)

    async def aggregate(
        self,
        serial_num: str,
        field: str,
        start_ms: int,
        end_ms: int,
        group_by: str = "hour",
        fn: str = "avg",
        tz_offset_minutes: int = 0,
    ) -> list[dict[str, float]]:
        """Bucketed aggregation. group_by: minute|hour|day|week|month|none.

        Returns [{bucket_start_ms, value, count}, ...] ordered ascending.
        For `none`, returns a single overall row (still in list form).
        """
        fn_map = {
            "avg": "AVG(value)",
            "sum": "SUM(value)",
            "min": "MIN(value)",
            "max": "MAX(value)",
            "count": "COUNT(value)",
        }
        if fn not in fn_map:
            raise ValueError(f"unknown fn {fn}")

        # SQLite's strftime works on seconds; we shift to local for the bucket
        # boundary, then shift back to UTC ms for the returned timestamps.
        local_sec = "((ts/1000) + ?*60)"
        boundary = {
            "minute": f"strftime('%Y-%m-%d %H:%M', {local_sec}, 'unixepoch')",
            "hour": f"strftime('%Y-%m-%d %H', {local_sec}, 'unixepoch')",
            "day": f"strftime('%Y-%m-%d', {local_sec}, 'unixepoch')",
            "week": f"strftime('%Y-%W', {local_sec}, 'unixepoch')",
            "month": f"strftime('%Y-%m', {local_sec}, 'unixepoch')",
        }
        if group_by == "none":
            sql = (
                f"SELECT {fn_map[fn]}, COUNT(value), MIN(ts), MAX(ts) FROM samples"
                " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
            )
            params = (serial_num, field, start_ms, end_ms)
        else:
            if group_by not in boundary:
                raise ValueError(f"unknown group_by {group_by}")
            sql = (
                f"SELECT {boundary[group_by]} AS b, {fn_map[fn]}, COUNT(value),"
                f" MIN(ts), MAX(ts) FROM samples"
                " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
                " GROUP BY b ORDER BY b"
            )
            params = (tz_offset_minutes, serial_num, field, start_ms, end_ms)

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()

        out = []
        if group_by == "none":
            for value, count, min_ts, max_ts in rows:
                if count == 0:
                    continue
                out.append({
                    "bucket": "all",
                    "value": float(value) if value is not None else None,
                    "count": int(count),
                    "first_ts": int(min_ts) if min_ts else None,
                    "last_ts": int(max_ts) if max_ts else None,
                })
        else:
            for b, value, count, min_ts, max_ts in rows:
                out.append({
                    "bucket": b,
                    "value": float(value) if value is not None else None,
                    "count": int(count),
                    "first_ts": int(min_ts) if min_ts else None,
                    "last_ts": int(max_ts) if max_ts else None,
                })
        return out

    async def overall_stats(
        self,
        serial_num: str,
        field: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, float]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COUNT(*), AVG(value), MIN(value), MAX(value), SUM(value)"
                " FROM samples WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?",
                (serial_num, field, start_ms, end_ms),
            )
            count, avg, mn, mx, total = await cur.fetchone()
        return {
            "count": int(count or 0),
            "avg": float(avg) if avg is not None else None,
            "min": float(mn) if mn is not None else None,
            "max": float(mx) if mx is not None else None,
            "sum": float(total) if total is not None else None,
        }

    async def date_coverage(
        self, serial_num: str, tz_offset_minutes: int
    ) -> dict[str, int]:
        """Return {YYYY-MM-DD: sample_count} for every local-time day we have data."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT date((ts/1000 + ?*60), 'unixepoch') AS d, COUNT(*)"
                " FROM samples WHERE serial_num = ?"
                " GROUP BY d ORDER BY d",
                (tz_offset_minutes, serial_num),
            )
            return {d: int(c) for d, c in await cur.fetchall() if d}

    async def list_fields(self, serial_num: str) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT DISTINCT category, field FROM samples"
                " WHERE serial_num = ? ORDER BY category, field",
                (serial_num,),
            )
            rows = await cur.fetchall()
            return [{"category": c, "field": f} for c, f in rows]

    async def query(
        self,
        serial_num: str,
        field: str,
        start_ms: int,
        end_ms: int,
        max_points: int = 1000,
    ) -> list[dict[str, float]]:
        """Return points within range. Downsamples by bucketing when needed.

        max_points caps the output so a wide range stays chart-friendly.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM samples"
                " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?",
                (serial_num, field, start_ms, end_ms),
            )
            (total,) = await cur.fetchone()
            if total == 0:
                return []
            if total <= max_points:
                cur = await db.execute(
                    "SELECT ts, value FROM samples"
                    " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
                    " ORDER BY ts",
                    (serial_num, field, start_ms, end_ms),
                )
                return [{"ts": ts, "value": v} for ts, v in await cur.fetchall()]
            # Downsample: average within buckets
            bucket_ms = max(1, (end_ms - start_ms) // max_points)
            cur = await db.execute(
                "SELECT (ts / ?) * ? AS bucket, AVG(value) FROM samples"
                " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
                " GROUP BY bucket ORDER BY bucket",
                (bucket_ms, bucket_ms, serial_num, field, start_ms, end_ms),
            )
            return [{"ts": int(ts), "value": float(v)} for ts, v in await cur.fetchall()]

    async def bucket_avg_by_time_of_day(
        self,
        serial_num: str,
        field: str,
        days: int = 7,
        bucket_minutes: int = 15,
        tz_offset_minutes: int = 0,
    ) -> dict[int, float]:
        """Average value per local-time bucket-of-day over the last `days`.

        Returns {minute_of_day: avg_value}. `tz_offset_minutes` shifts UTC ts
        into local time before bucketing (e.g. America/Tijuana in summer = -420).
        """
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - days * 86_400_000
        # bucket = floor((local_minutes) / bucket_minutes) * bucket_minutes
        # local_minutes = ((ts/60000) + tz_offset_minutes) mod 1440
        sql = (
            "SELECT (((ts/60000 + ?) % 1440) / ?) * ? AS bucket, AVG(value)"
            " FROM samples"
            " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
            " GROUP BY bucket ORDER BY bucket"
        )
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                sql,
                (tz_offset_minutes, bucket_minutes, bucket_minutes,
                 serial_num, field, start_ms, end_ms),
            )
            rows = await cur.fetchall()
        return {int(b): float(v) for b, v in rows if v is not None}

    async def bucket_max_by_time_of_day(
        self,
        serial_num: str,
        field: str,
        days: int = 30,
        bucket_minutes: int = 15,
        tz_offset_minutes: int = 0,
    ) -> dict[int, float]:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - days * 86_400_000
        sql = (
            "SELECT (((ts/60000 + ?) % 1440) / ?) * ? AS bucket, MAX(value)"
            " FROM samples"
            " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
            " GROUP BY bucket ORDER BY bucket"
        )
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                sql,
                (tz_offset_minutes, bucket_minutes, bucket_minutes,
                 serial_num, field, start_ms, end_ms),
            )
            rows = await cur.fetchall()
        return {int(b): float(v) for b, v in rows if v is not None}

    async def first_sample_ts(self, serial_num: str, field: str) -> int | None:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT MIN(ts) FROM samples WHERE serial_num = ? AND field = ?",
                (serial_num, field),
            )
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None

    async def known_fields(self, serial_num: str) -> set[str]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT DISTINCT field FROM samples WHERE serial_num = ?",
                (serial_num,),
            )
            return {r[0] for r in await cur.fetchall()}

    # ---------- sites ----------
    async def list_sites(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM sites WHERE enabled = 1 ORDER BY created_at")
            return [dict(r) for r in await cur.fetchall()]

    async def get_site(self, site_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def upsert_site(self, site: dict[str, Any]) -> None:
        import json as _json, time as _time
        if "created_at" not in site:
            site["created_at"] = int(_time.time())
        cols = ["id", "name", "vendor", "lat", "lon", "tz", "peak_kw",
                "battery_capacity_kwh", "max_charge_kw", "config_json",
                "credentials_json", "created_at", "enabled"]
        vals = []
        for c in cols:
            v = site.get(c)
            if c in ("config_json", "credentials_json") and isinstance(v, dict):
                v = _json.dumps(v)
            if c == "enabled" and v is None:
                v = 1
            vals.append(v)
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join(cols)
        update_set = ",".join([f"{c} = excluded.{c}" for c in cols if c != "id"])
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"INSERT INTO sites ({col_list}) VALUES ({placeholders})"
                f" ON CONFLICT(id) DO UPDATE SET {update_set}",
                vals,
            )
            await db.commit()

    async def delete_site(self, site_id: str, cascade: bool = False) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            if cascade:
                await db.execute("DELETE FROM samples WHERE site_id = ?", (site_id,))
                await db.execute("DELETE FROM appliances WHERE site_id = ?", (site_id,))
                await db.execute("DELETE FROM alerts WHERE site_id = ?", (site_id,))
            await db.execute("DELETE FROM sites WHERE id = ?", (site_id,))
            await db.commit()

    # ---------- appliances ----------
    async def list_appliances(self, site_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM appliances WHERE site_id = ? ORDER BY id", (site_id,)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def upsert_appliance(self, appl: dict[str, Any]) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if appl.get("id"):
                await db.execute(
                    "UPDATE appliances SET name=?, watts=?, typical_minutes=?,"
                    " can_defer=?, preferred_start_hour=?, preferred_end_hour=?,"
                    " enabled=? WHERE id=? AND site_id=?",
                    (appl["name"], appl["watts"], appl["typical_minutes"],
                     int(appl.get("can_defer", 1)),
                     appl.get("preferred_start_hour"),
                     appl.get("preferred_end_hour"),
                     int(appl.get("enabled", 1)), appl["id"], appl["site_id"]),
                )
                await db.commit()
                return appl["id"]
            cur = await db.execute(
                "INSERT INTO appliances (site_id, name, watts, typical_minutes,"
                " can_defer, preferred_start_hour, preferred_end_hour, enabled)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (appl["site_id"], appl["name"], appl["watts"],
                 appl["typical_minutes"], int(appl.get("can_defer", 1)),
                 appl.get("preferred_start_hour"),
                 appl.get("preferred_end_hour"),
                 int(appl.get("enabled", 1))),
            )
            await db.commit()
            return cur.lastrowid

    async def delete_appliance(self, appliance_id: int, site_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM appliances WHERE id = ? AND site_id = ?",
                (appliance_id, site_id),
            )
            await db.commit()

    # ---------- alerts ----------
    async def list_alerts(self, site_id: str, limit: int = 50,
                          unacknowledged_only: bool = False) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            where = "WHERE site_id = ?"
            params: list[Any] = [site_id]
            if unacknowledged_only:
                where += " AND acknowledged = 0"
            cur = await db.execute(
                f"SELECT * FROM alerts {where} ORDER BY ts DESC LIMIT ?",
                (*params, limit),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def record_alert(self, site_id: str, severity: str, rule: str, message: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO alerts (site_id, ts, severity, rule, message)"
                " VALUES (?, ?, ?, ?, ?)",
                (site_id, int(time.time() * 1000), severity, rule, message),
            )
            await db.commit()
            return cur.lastrowid

    async def acknowledge_alert(self, alert_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
            await db.commit()

    # ------------------------- network connectivity ------------------------
    async def record_network_check(
        self, ts_ms: int, target: str, ok: bool,
        latency_ms: int | None, error: str | None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO network_checks (ts, target, ok, latency_ms, error)"
                " VALUES (?, ?, ?, ?, ?)",
                (ts_ms, target, 1 if ok else 0, latency_ms, error),
            )
            await db.commit()

    async def list_network_checks(
        self, since_ms: int, limit: int = 5000,
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT ts, target, ok, latency_ms, error FROM network_checks"
                " WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
                (since_ms, limit),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def network_summary(
        self, since_ms: int, end_ms: int | None = None,
    ) -> dict[str, Any]:
        """Aggregate stats over a window: total probes, successes, avg
        latency of successful probes, last check timestamp. ``end_ms``
        is exclusive; omit for open-ended (up to now)."""
        params: list[Any] = [since_ms]
        where = "ts >= ?"
        if end_ms is not None:
            where += " AND ts < ?"
            params.append(end_ms)
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                f"SELECT COUNT(*) AS total,"
                f" COALESCE(SUM(ok), 0) AS ok_count,"
                f" MAX(ts) AS last_ts,"
                f" AVG(CASE WHEN ok=1 THEN latency_ms END) AS avg_latency"
                f" FROM network_checks WHERE {where}",
                params,
            )
            row = await cur.fetchone()
            return {
                "total": row[0] or 0,
                "ok_count": row[1] or 0,
                "last_ts": row[2],
                "avg_latency_ms": row[3],
            }

    async def network_outages_in_range(
        self, start_ms: int, end_ms: int,
    ) -> list[dict[str, Any]]:
        """Outages whose active window overlaps [start_ms, end_ms)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM network_outages"
                " WHERE started_ts < ?"
                " AND (ended_ts IS NULL OR ended_ts > ?)"
                " ORDER BY started_ts ASC",
                (end_ms, start_ms),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def latest_network_check(self) -> dict[str, Any] | None:
        """Most-recent per-check row across all targets, with any_ok flag
        computed over the same wall-clock probe cycle (ts within 5s)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT MAX(ts) AS ts FROM network_checks",
            )
            row = await cur.fetchone()
            if not row or row["ts"] is None:
                return None
            latest_ts = row["ts"]
            cur = await db.execute(
                "SELECT target, ok, latency_ms, error, ts FROM network_checks"
                " WHERE ts BETWEEN ? AND ?",
                (latest_ts - 5000, latest_ts),
            )
            rows = [dict(r) for r in await cur.fetchall()]
            any_ok = any(r["ok"] for r in rows)
            return {"ts": latest_ts, "any_ok": any_ok, "probes": rows}

    async def open_network_outage(self, started_ts: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO network_outages (started_ts) VALUES (?)",
                (started_ts,),
            )
            await db.commit()
            return cur.lastrowid

    async def close_network_outage(
        self, outage_id: int, ended_ts: int, notified: bool = False,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE network_outages SET ended_ts = ?,"
                " duration_seconds = (? - started_ts) / 1000,"
                " notified = ?"
                " WHERE id = ?",
                (ended_ts, ended_ts, 1 if notified else 0, outage_id),
            )
            await db.commit()

    async def get_open_network_outage(self) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM network_outages"
                " WHERE ended_ts IS NULL ORDER BY id DESC LIMIT 1",
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def list_network_outages(self, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM network_outages"
                " ORDER BY started_ts DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def prune_network_checks(self, older_than_ms: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM network_checks WHERE ts < ?", (older_than_ms,),
            )
            await db.commit()
            return cur.rowcount

    async def get_settings(self) -> dict[str, str]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT key, value FROM settings")
            return {k: v for k, v in await cur.fetchall()}

    async def set_settings(self, items: dict[str, str]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(items.items()),
            )
            await db.commit()

    # ------------------------- web session tokens ---------------------------
    async def save_web_session(self, token: str, username: str) -> None:
        import time as _time
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO web_sessions(token, username, created_at) VALUES (?,?,?)"
                " ON CONFLICT(token) DO UPDATE SET username=excluded.username",
                (token, username, _time.time()),
            )
            await db.commit()

    async def get_web_session_username(self, token: str) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT username FROM web_sessions WHERE token=?", (token,),
            )
            row = await cur.fetchone()
        return row[0] if row else None

    async def drop_web_session(self, token: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM web_sessions WHERE token=?", (token,))
            await db.commit()

    async def prune_web_sessions(self, older_than_seconds: float = 30 * 86400) -> int:
        """Delete tokens older than the given age. Returns rows removed."""
        import time as _time
        cutoff = _time.time() - older_than_seconds
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM web_sessions WHERE created_at < ?", (cutoff,),
            )
            await db.commit()
            return cur.rowcount or 0

    # ------------------------- announcement history ------------------------
    async def log_announcement(
        self, source: str, text: str, channels: list[str], ok: bool,
        detail: str | None = None,
    ) -> None:
        import time as _time
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO announcement_history(ts, source, text, channels, ok, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_time.time(), source, text, ",".join(channels or []),
                 int(bool(ok)), detail),
            )
            await db.commit()

    async def recent_announcements(
        self, limit: int = 100, since_seconds: float | None = None,
    ) -> list[dict]:
        import time as _time
        params: tuple = ()
        where = ""
        if since_seconds:
            where = "WHERE ts >= ?"
            params = (_time.time() - since_seconds,)
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT id, ts, source, text, channels, ok, detail "
                "FROM announcement_history "
                f"{where} ORDER BY ts DESC LIMIT ?",
                params + (limit,),
            )
            rows = await cur.fetchall()
        return [
            {
                "id": r[0], "ts": r[1], "source": r[2], "text": r[3],
                "channels": r[4].split(",") if r[4] else [],
                "ok": bool(r[5]), "detail": r[6],
            }
            for r in rows
        ]

    async def prune_announcements(self, older_than_seconds: float = 30 * 86400) -> int:
        import time as _time
        cutoff = _time.time() - older_than_seconds
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM announcement_history WHERE ts < ?", (cutoff,),
            )
            await db.commit()
            return cur.rowcount or 0

    async def latest(self, serial_num: str, fields: Iterable[str]) -> dict[str, dict[str, float]]:
        """Most recent value for each field. Used by the UI to fill tiles."""
        out: dict[str, dict[str, float]] = {}
        async with aiosqlite.connect(self.db_path) as db:
            for f in fields:
                cur = await db.execute(
                    "SELECT ts, value FROM samples"
                    " WHERE serial_num = ? AND field = ?"
                    " ORDER BY ts DESC LIMIT 1",
                    (serial_num, f),
                )
                row = await cur.fetchone()
                if row:
                    out[f] = {"ts": row[0], "value": row[1]}
        return out
