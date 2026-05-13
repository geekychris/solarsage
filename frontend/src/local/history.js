// Local SQLite history — port of backend/app/storage.py's `samples` table and
// query/aggregate helpers, sitting on @capacitor-community/sqlite.
//
// Tall/skinny schema: every numeric field becomes its own (serial, ts, category,
// field, value) row, so we can drop new metrics in without migrations — same
// shape as the FastAPI backend uses, which lets the React UI consume both
// stores interchangeably.

import { CapacitorSQLite, SQLiteConnection } from "@capacitor-community/sqlite";
import { Capacitor } from "@capacitor/core";

const DB_NAME = "solarsage";
const sqlite = new SQLiteConnection(CapacitorSQLite);

const SCHEMA = `
CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  serial_num TEXT NOT NULL,
  ts INTEGER NOT NULL,
  category TEXT NOT NULL,
  field TEXT NOT NULL,
  value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_lookup ON samples(serial_num, field, ts);
CREATE INDEX IF NOT EXISTS idx_samples_recent ON samples(serial_num, ts);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
`;

class History {
  constructor() {
    this.db = null;
    this.initPromise = null;
  }

  async _init() {
    if (this.db) return this.db;
    if (this.initPromise) return this.initPromise;
    this.initPromise = (async () => {
      // On iOS/Android we open an encrypted-capable SQLite; the web fallback
      // would need jeep-sqlite, which we don't ship — this module is only
      // imported from local/server.js which itself is only loaded in native.
      const isNative = Capacitor.isNativePlatform();
      if (!isNative) {
        throw new Error("local history is only available on native builds");
      }
      const conn = await sqlite.createConnection(DB_NAME, false, "no-encryption", 1, false);
      await conn.open();
      await conn.execute(SCHEMA);
      this.db = conn;
      return conn;
    })();
    return this.initPromise;
  }

  static _flatten(data) {
    const out = [];
    for (const [k, v] of Object.entries(data || {})) {
      if (k.startsWith("_")) continue;
      if (typeof v === "boolean") continue;
      if (typeof v === "number" && Number.isFinite(v)) out.push([k, v]);
    }
    return out;
  }

  async record(serial, category, data, tsMs) {
    const db = await this._init();
    const ts = tsMs ?? Date.now();
    const rows = History._flatten(data);
    if (!rows.length) return 0;
    const stmts = rows.map(([f, v]) => ({
      statement:
        "INSERT INTO samples (serial_num, ts, category, field, value) VALUES (?,?,?,?,?)",
      values: [serial, ts, category, f, v],
    }));
    await db.executeSet(stmts);
    return rows.length;
  }

  async upsertMany(serial, category, samples) {
    if (!samples.length) return 0;
    const db = await this._init();
    const stmts = [];
    for (const [ts, fields] of samples) {
      for (const [f, v] of Object.entries(fields)) {
        if (typeof v !== "number" || !Number.isFinite(v)) continue;
        stmts.push({
          statement:
            "DELETE FROM samples WHERE serial_num=? AND ts=? AND category=? AND field=?",
          values: [serial, ts, category, f],
        });
        stmts.push({
          statement:
            "INSERT INTO samples (serial_num, ts, category, field, value) VALUES (?,?,?,?,?)",
          values: [serial, ts, category, f, v],
        });
      }
    }
    if (!stmts.length) return 0;
    await db.executeSet(stmts);
    return stmts.length / 2;
  }

  async query(serial, field, startMs, endMs, maxPoints = 1000) {
    const db = await this._init();
    const countRow = await db.query(
      "SELECT COUNT(*) AS c FROM samples WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ?",
      [serial, field, startMs, endMs],
    );
    const total = countRow.values?.[0]?.c || 0;
    if (total === 0) return [];
    if (total <= maxPoints) {
      const r = await db.query(
        "SELECT ts, value FROM samples WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ? ORDER BY ts",
        [serial, field, startMs, endMs],
      );
      return (r.values || []).map((row) => ({ ts: row.ts, value: row.value }));
    }
    const bucket = Math.max(1, Math.floor((endMs - startMs) / maxPoints));
    const r = await db.query(
      `SELECT (ts/?)*? AS b, AVG(value) AS v FROM samples
        WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ?
        GROUP BY b ORDER BY b`,
      [bucket, bucket, serial, field, startMs, endMs],
    );
    return (r.values || []).map((row) => ({ ts: row.b, value: row.v }));
  }

  async aggregate(serial, field, startMs, endMs, groupBy = "hour", fn = "avg", tzOffsetMinutes = 0) {
    const db = await this._init();
    const fnMap = { avg: "AVG(value)", sum: "SUM(value)", min: "MIN(value)", max: "MAX(value)", count: "COUNT(value)" };
    if (!fnMap[fn]) throw new Error(`unknown fn ${fn}`);
    const localSec = `((ts/1000) + ?*60)`;
    const boundary = {
      minute: `strftime('%Y-%m-%d %H:%M', ${localSec}, 'unixepoch')`,
      hour:   `strftime('%Y-%m-%d %H',    ${localSec}, 'unixepoch')`,
      day:    `strftime('%Y-%m-%d',       ${localSec}, 'unixepoch')`,
      week:   `strftime('%Y-%W',          ${localSec}, 'unixepoch')`,
      month:  `strftime('%Y-%m',          ${localSec}, 'unixepoch')`,
    };
    if (groupBy === "none") {
      const r = await db.query(
        `SELECT ${fnMap[fn]} AS v, COUNT(value) AS c, MIN(ts) AS mn, MAX(ts) AS mx
           FROM samples WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ?`,
        [serial, field, startMs, endMs],
      );
      const row = r.values?.[0];
      if (!row || !row.c) return [];
      return [{ bucket: "all", value: row.v, count: row.c, first_ts: row.mn, last_ts: row.mx }];
    }
    if (!boundary[groupBy]) throw new Error(`unknown group_by ${groupBy}`);
    const r = await db.query(
      `SELECT ${boundary[groupBy]} AS b, ${fnMap[fn]} AS v, COUNT(value) AS c,
              MIN(ts) AS mn, MAX(ts) AS mx
         FROM samples WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ?
        GROUP BY b ORDER BY b`,
      [tzOffsetMinutes, serial, field, startMs, endMs],
    );
    return (r.values || []).map((row) => ({
      bucket: row.b,
      value: row.v,
      count: row.c,
      first_ts: row.mn,
      last_ts: row.mx,
    }));
  }

  async bucketAvgByTimeOfDay(serial, field, days = 7, bucketMinutes = 15, tzOffsetMinutes = 0) {
    const db = await this._init();
    const endMs = Date.now();
    const startMs = endMs - days * 86_400_000;
    const r = await db.query(
      `SELECT (((ts/60000 + ?) % 1440) / ?) * ? AS b, AVG(value) AS v
         FROM samples WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ?
        GROUP BY b ORDER BY b`,
      [tzOffsetMinutes, bucketMinutes, bucketMinutes, serial, field, startMs, endMs],
    );
    const out = {};
    for (const row of r.values || []) if (row.v != null) out[row.b] = row.v;
    return out;
  }

  async bucketMaxByTimeOfDay(serial, field, days = 30, bucketMinutes = 15, tzOffsetMinutes = 0) {
    const db = await this._init();
    const endMs = Date.now();
    const startMs = endMs - days * 86_400_000;
    const r = await db.query(
      `SELECT (((ts/60000 + ?) % 1440) / ?) * ? AS b, MAX(value) AS v
         FROM samples WHERE serial_num=? AND field=? AND ts BETWEEN ? AND ?
        GROUP BY b ORDER BY b`,
      [tzOffsetMinutes, bucketMinutes, bucketMinutes, serial, field, startMs, endMs],
    );
    const out = {};
    for (const row of r.values || []) if (row.v != null) out[row.b] = row.v;
    return out;
  }

  async knownFields(serial) {
    const db = await this._init();
    const r = await db.query("SELECT DISTINCT field FROM samples WHERE serial_num=?", [serial]);
    return new Set((r.values || []).map((x) => x.field));
  }

  async listFields(serial) {
    const db = await this._init();
    const r = await db.query(
      "SELECT DISTINCT category, field FROM samples WHERE serial_num=? ORDER BY category, field",
      [serial],
    );
    return (r.values || []).map((x) => ({ category: x.category, field: x.field }));
  }

  async firstSampleTs(serial, field) {
    const db = await this._init();
    const r = await db.query(
      "SELECT MIN(ts) AS m FROM samples WHERE serial_num=? AND field=?",
      [serial, field],
    );
    return r.values?.[0]?.m ?? null;
  }

  async dateCoverage(serial, tzOffsetMinutes = 0) {
    const db = await this._init();
    const r = await db.query(
      `SELECT date((ts/1000 + ?*60), 'unixepoch') AS d, COUNT(*) AS c
         FROM samples WHERE serial_num=?
        GROUP BY d ORDER BY d`,
      [tzOffsetMinutes, serial],
    );
    const out = {};
    for (const row of r.values || []) if (row.d) out[row.d] = row.c;
    return out;
  }

  async latest(serial, fields) {
    const db = await this._init();
    const out = {};
    for (const f of fields) {
      const r = await db.query(
        "SELECT ts, value FROM samples WHERE serial_num=? AND field=? ORDER BY ts DESC LIMIT 1",
        [serial, f],
      );
      const row = r.values?.[0];
      if (row) out[f] = { ts: row.ts, value: row.value };
    }
    return out;
  }

  async getSettings() {
    const db = await this._init();
    const r = await db.query("SELECT key, value FROM settings");
    const out = {};
    for (const row of r.values || []) out[row.key] = row.value;
    return out;
  }

  async setSettings(items) {
    const db = await this._init();
    const stmts = Object.entries(items).map(([k, v]) => ({
      statement:
        "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      values: [k, v],
    }));
    if (stmts.length) await db.executeSet(stmts);
  }
}

export const history = new History();
