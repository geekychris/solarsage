// EG4 portal client — TypeScript port of eg4_inverter_api.client + eg4_history.
//
// Talks to monitor.eg4electronics.com directly using CapacitorHttp (which
// bypasses the WebView CORS sandbox by routing through native code).

import { CapacitorHttp } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";
import { history } from "./history.js";

const BASE_URL = "https://monitor.eg4electronics.com";
const CREDS_KEY = "eg4.credentials";

const PATHS = {
  login: "/WManage/api/login",
  runtime: "/WManage/api/inverter/getInverterRuntime",
  energy: "/WManage/api/inverter/getInverterEnergyInfo",
  battery: "/WManage/api/battery/getBatteryInfo",
  dayLine: "/WManage/api/analyze/chart/dayLine",
};

const CHART_ATTRS = [
  "ppv1", "ppv2", "ppv3", "ppv4",
  "pCharge", "pDisCharge", "pToGrid", "pToUser",
  "peps", "pEpsL1N", "pEpsL2N",
  "soc", "vBat", "bmsBatCurrent",
  "vacr", "vacs", "vact", "fac",
  "vpv1", "vpv2", "vpv3",
  "tBat", "tinner", "tradiator1", "tradiator2",
  "feps", "vepsr", "vepss", "vepst",
  "acCouplePower", "status",
];

class EG4Client {
  constructor() {
    this.username = null;
    this.password = null;
    this.inverters = [];
    this.loggedIn = false;
  }

  async _post(path, formObj) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(formObj || {})) params.set(k, String(v));
    const res = await CapacitorHttp.post({
      url: `${BASE_URL}${path}`,
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json, text/plain, */*",
      },
      data: params.toString(),
    });
    // CapacitorHttp persists cookies in the native cookie jar automatically.
    if (res.status === 401 && this.username) {
      await this._loginInternal(this.username, this.password);
      const retry = await CapacitorHttp.post({
        url: `${BASE_URL}${path}`,
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json, text/plain, */*",
        },
        data: params.toString(),
      });
      return parseJson(retry);
    }
    if (res.status >= 400) {
      throw Object.assign(new Error(`EG4 ${path} → HTTP ${res.status}`), {
        status: res.status,
      });
    }
    return parseJson(res);
  }

  async _loginInternal(username, password) {
    const body = await this._post(PATHS.login, { account: username, password });
    if (!body.success) {
      throw Object.assign(new Error("Login failed — check credentials"), { status: 401 });
    }
    this.username = username;
    this.password = password;
    this.loggedIn = true;
    this.inverters = [];
    for (const plant of body.plants || []) {
      for (const inv of plant.inverters || []) {
        this.inverters.push({
          ...inv,
          plantId: plant.plantId,
          plantName: plant.name,
        });
      }
    }
    return { inverters: this.inverters, username };
  }

  async login(username, password) {
    return this._loginInternal(username, password);
  }

  async logout() {
    this.loggedIn = false;
    this.inverters = [];
    // CapacitorHttp doesn't expose a clear-cookies API; the session will
    // expire server-side and re-login will refresh.
  }

  isLoggedIn() {
    return this.loggedIn;
  }

  getInverters() {
    return this.inverters;
  }

  async saveCredentials(username, password) {
    await Preferences.set({ key: CREDS_KEY, value: JSON.stringify({ username, password }) });
  }

  async clearCredentials() {
    await Preferences.remove({ key: CREDS_KEY });
  }

  async hasSavedCredentials() {
    const r = await Preferences.get({ key: CREDS_KEY });
    return !!r.value;
  }

  async loginFromSaved() {
    const r = await Preferences.get({ key: CREDS_KEY });
    if (!r.value) throw Object.assign(new Error("no saved credentials"), { status: 404 });
    const { username, password } = JSON.parse(r.value);
    return this._loginInternal(username, password);
  }

  // Ensure we have a live EG4 session before any authed call. After an app
  // restart the in-memory session is gone; if saved credentials exist, silently
  // re-login. Otherwise throw 401 so App.jsx falls back to the login screen.
  async ensureLoggedIn() {
    if (this.loggedIn && this.inverters.length) return;
    if (await this.hasSavedCredentials()) {
      await this.loginFromSaved();
      // Restart the poller after auto-recovery
      const { poller } = await import("./poller.js");
      await poller.start();
      return;
    }
    throw Object.assign(new Error("not logged in"), { status: 401 });
  }

  async runtime(serial) {
    return this._post(PATHS.runtime, { serialNum: serial });
  }
  async energy(serial) {
    return this._post(PATHS.energy, { serialNum: serial });
  }
  async battery(serial) {
    return this._post(PATHS.battery, { serialNum: serial });
  }

  async snapshot(serial) {
    const [r, e, b] = await Promise.all([
      this.runtime(serial),
      this.energy(serial),
      this.battery(serial),
    ]);
    // Persist the numeric scalars so the local SQLite history accumulates.
    await history.record(serial, "runtime", r);
    await history.record(serial, "energy", e);
    const { batteryArray, ...battery } = b || {};
    await history.record(serial, "battery", battery);
    for (const unit of batteryArray || []) {
      const i = unit.batIndex;
      if (i == null) continue;
      await history.record(serial, "battery_unit", {
        [`unit${i}_soc`]: unit.soc,
        [`unit${i}_soh`]: unit.soh,
        [`unit${i}_voltage`]: unit.totalVoltage,
        [`unit${i}_current`]: unit.current,
        [`unit${i}_cycles`]: unit.cycleCnt,
      });
    }
    return { runtime: r, energy: e, battery: b };
  }

  // ------------------------------------------------------------------
  // Historical backfill — per-attribute dayLine endpoint
  // ------------------------------------------------------------------
  async _dayLineAttr(serial, dateText, attr, tzOffsetMinutes) {
    const body = await this._post(PATHS.dayLine, {
      serialNum: serial,
      attr,
      dateText,
    });
    if (!body.success) return [];
    const out = [];
    for (const p of body.data || []) {
      const v = p.value;
      if (typeof v !== "number") continue;
      const ts = parseTimeString(p.time, tzOffsetMinutes);
      if (ts == null) continue;
      out.push({ ts, attr, value: v });
    }
    return out;
  }

  async fetchDay(serial, dateText, tzOffsetMinutes, concurrency = 4) {
    const queue = [...CHART_ATTRS];
    const merged = new Map(); // ts -> { field: value }
    async function worker(client) {
      while (queue.length) {
        const attr = queue.shift();
        const points = await client._dayLineAttr(serial, dateText, attr, tzOffsetMinutes);
        for (const p of points) {
          const slot = merged.get(p.ts) || {};
          slot[p.attr] = p.value;
          merged.set(p.ts, slot);
        }
      }
    }
    await Promise.all(Array.from({ length: concurrency }, () => worker(this)));
    // Synthesize ppv = sum of strings, consumptionPower = pEpsL1N + pEpsL2N
    for (const fields of merged.values()) {
      if (!("ppv" in fields)) {
        const strings = ["ppv1", "ppv2", "ppv3", "ppv4"].map((s) => fields[s] || 0);
        if (strings.some((s) => s !== 0)) fields.ppv = strings.reduce((a, b) => a + b, 0);
      }
      if (!("consumptionPower" in fields) && ("pEpsL1N" in fields || "pEpsL2N" in fields)) {
        fields.consumptionPower = (fields.pEpsL1N || 0) + (fields.pEpsL2N || 0);
      }
    }
    return [...merged.entries()].sort((a, b) => a[0] - b[0]).map(([ts, fields]) => ({ ts, fields }));
  }

  async syncHistory(serial, days = 30) {
    // Pull "days" days back from today (local tz) into the local history db.
    const tzOff = await (await import("./forecast.js")).tzOffsetMinutes();
    const todayLocal = new Date(Date.now() + tzOff * 60_000);
    const results = [];
    let totalValues = 0;
    let totalPoints = 0;
    for (let back = days - 1; back >= 0; back--) {
      const d = new Date(todayLocal);
      d.setUTCDate(d.getUTCDate() - back);
      const dateText = d.toISOString().slice(0, 10);
      try {
        const samples = await this.fetchDay(serial, dateText, tzOff);
        const tuples = samples.map((s) => [s.ts, s.fields]);
        const written = await history.upsertMany(serial, "historical", tuples);
        totalValues += written;
        totalPoints += samples.length;
        results.push({ date: dateText, ok: true, points: samples.length, values: written });
      } catch (exc) {
        results.push({ date: dateText, ok: false, error: String(exc.message || exc) });
      }
    }
    return {
      serial,
      days_requested: days,
      total_points: totalPoints,
      total_values_written: totalValues,
      days: results,
    };
  }

  async diagnostic(serial) {
    const out = { serial };
    try { out.runtime = { fields: await this.runtime(serial) }; } catch (e) { out.runtime = { error: String(e) }; }
    try { out.energy = { fields: await this.energy(serial) }; } catch (e) { out.energy = { error: String(e) }; }
    try { out.battery = { fields: await this.battery(serial) }; } catch (e) { out.battery = { error: String(e) }; }
    out.stored_fields = await history.knownFields(serial);
    return out;
  }
}

function parseJson(res) {
  if (typeof res.data === "object" && res.data !== null) return res.data;
  try {
    return JSON.parse(res.data);
  } catch {
    throw new Error(`Unexpected non-JSON response from EG4: ${String(res.data).slice(0, 200)}`);
  }
}

function parseTimeString(timeStr, tzOffsetMinutes) {
  // Format: "YYYY-MM-DD HH:MM:SS" in local time
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(timeStr || "");
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m;
  // Compute UTC ms by treating the local time as if it were UTC, then offsetting.
  const localAsUtc = Date.UTC(+y, +mo - 1, +d, +h, +mi, s ? +s : 0);
  return localAsUtc - tzOffsetMinutes * 60_000;
}

export const eg4 = new EG4Client();
