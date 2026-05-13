// In-app "backend" for the Capacitor (iOS/Android) build.
//
// Maps the same `/api/*` paths that the FastAPI server exposes to local
// handler functions that hit EG4 directly + persist to a local SQLite db.
// The React components in src/components/ call api.js exactly the same way
// in both builds — only the dispatch target changes.
//
// Each handler is async ({query, body}) => responseObject.

import { eg4 } from "./eg4Client.js";
import { history } from "./history.js";
import { poller } from "./poller.js";
import * as forecast from "./forecast.js";
import * as weather from "./weather.js";
import { seedForSite } from "./appliancesCatalog.js";

function notImplemented(name) {
  return async () => {
    throw Object.assign(new Error(`${name} not yet ported to native build`), {
      status: 501,
    });
  };
}

// Wrap a handler so it auto-recovers the EG4 session after an app restart.
function authed(fn) {
  return async (ctx) => {
    await eg4.ensureLoggedIn();
    return fn(ctx);
  };
}

export const handlers = {
  // --- Auth ---
  "POST /api/login": async ({ body }) => {
    const r = await eg4.login(body.username, body.password);
    if (body.remember) await eg4.saveCredentials(body.username, body.password);
    await poller.start();
    return {
      token: "native-session",
      username: body.username,
      inverter_count: r.inverters.length,
      remembered: !!body.remember,
    };
  },
  "POST /api/logout": async ({ query }) => {
    await eg4.logout();
    if (query.forget === "true") await eg4.clearCredentials();
    poller.stop();
    return { ok: true, credentials_forgotten: query.forget === "true" };
  },
  "GET /api/auth/status": async () => ({
    credentials_persisted: await eg4.hasSavedCredentials(),
    active_sessions: eg4.isLoggedIn() ? 1 : 0,
  }),
  "POST /api/auth/use_saved": async () => {
    const r = await eg4.loginFromSaved();
    await poller.start();
    return {
      token: "native-session",
      username: r.username,
      inverter_count: r.inverters.length,
    };
  },

  // --- Inverters & live data ---
  "GET /api/inverters": authed(async () => ({
    username: eg4.username,
    inverters: eg4.getInverters(),
  })),
  "GET /api/snapshot": authed(async ({ query }) => {
    const snap = await eg4.snapshot(query.serial);
    return { serial: query.serial, ts: Date.now(), ...snap };
  }),
  "GET /api/runtime": authed(async ({ query }) => ({
    serial: query.serial,
    ts: Date.now(),
    data: await eg4.runtime(query.serial),
  })),
  "GET /api/energy": authed(async ({ query }) => ({
    serial: query.serial,
    ts: Date.now(),
    data: await eg4.energy(query.serial),
  })),
  "GET /api/battery": authed(async ({ query }) => ({
    serial: query.serial,
    ts: Date.now(),
    data: await eg4.battery(query.serial),
  })),

  // --- History queries (against local SQLite) ---
  "GET /api/metrics": async ({ query }) => ({
    serial: query.serial,
    metrics: await history.listFields(query.serial),
  }),
  "GET /api/history": async ({ query }) => {
    const end = Number(query.end) || Date.now();
    const minutes = Number(query.range_minutes) || 60;
    const start = Number(query.start) || end - minutes * 60_000;
    const points = await history.query(
      query.serial,
      query.field,
      start,
      end,
      Number(query.max_points) || 1000,
    );
    return { serial: query.serial, field: query.field, start, end, points };
  },
  "GET /api/range": async ({ query }) => forecast.rangeQuery(query),
  "GET /api/daychart": async ({ query }) => forecast.dayChart(query),
  "GET /api/aggregate": async ({ query }) => forecast.aggregate(query),
  "GET /api/coverage": async ({ query }) => ({
    serial: query.serial,
    tz_offset_minutes: await forecast.tzOffsetMinutes(),
    by_date: await history.dateCoverage(query.serial),
  }),

  // --- Settings ---
  "GET /api/settings": async () => forecast.getSettings(),
  "PUT /api/settings": async ({ body }) => forecast.putSettings(body),

  // --- Forecasts ---
  "GET /api/forecast/solar_today": async ({ query }) => forecast.solarToday(query.serial),
  "GET /api/forecast/battery_completion": async ({ query }) =>
    forecast.batteryCompletion(query.serial),
  "GET /api/forecast/excess": async ({ query }) => forecast.excessToday(query.serial),
  "GET /api/forecast/max_production": async () => forecast.maxProduction(),
  "GET /api/forecast/tomorrow": async ({ query }) => forecast.tomorrow(query.serial),
  "GET /api/weather": async ({ query }) => weather.forecast(Number(query.days) || 7),

  // --- Battery cycle (the panel we added recently) ---
  "GET /api/battery_cycles": async ({ query }) =>
    forecast.batteryCycles(query.serial, Number(query.days) || 14),

  // --- Sync (one-shot backfill) ---
  "POST /api/sync": async ({ query }) =>
    eg4.syncHistory(query.serial, Number(query.days) || 30),
  "POST /api/backfill": async ({ query }) =>
    eg4.syncHistory(query.serial, Number(query.days) || 14),

  // --- Appliances (local CRUD against SQLite) ---
  "GET /api/appliances": async ({ query }) => {
    const siteId = query.site_id || "site-1";
    let appliances = await history.listAppliances(siteId);
    if (!appliances.length) {
      // First time we're asked — seed the default catalog so the user has
      // something to enable/disable, matching the backend's upsert_site flow.
      for (const a of seedForSite(siteId)) await history.upsertAppliance(a);
      appliances = await history.listAppliances(siteId);
    }
    return { site_id: siteId, appliances };
  },
  "POST /api/appliances": async ({ body }) => {
    if (!body?.site_id || !body?.name || body.watts == null) {
      throw Object.assign(new Error("site_id, name, watts required"), { status: 400 });
    }
    const id = await history.upsertAppliance(body);
    return { id };
  },
  "DELETE /api/appliances/:id": async ({ params, query }) => {
    await history.deleteAppliance(params.id, query.site_id || "site-1");
    return { ok: true };
  },

  // --- Performance trend (actual vs irradiance-expected kWh) ---
  "GET /api/performance": async ({ query }) => forecast.performance(query),

  // --- Things still pending (multi-site, scheduler) ---
  "GET /api/sites": notImplemented("sites"),
  "POST /api/sites": notImplemented("upsert site"),
  "GET /api/schedule": notImplemented("schedule"),
  "GET /api/heatmap": async ({ query }) => forecast.heatmap(query),
  "GET /api/string_health": async ({ query }) => forecast.stringHealth(query),
  "GET /api/alerts": async ({ query }) => ({ site_id: query.site_id, alerts: [] }),
  "POST /api/alerts/ack": async () => ({ ok: true }),
  "GET /api/health": async () => ({ ok: true, native: true }),
  "GET /api/diagnostic": async ({ query }) => eg4.diagnostic(query.serial),
  "GET /api/summary": notImplemented("summary"),
  "GET /api/best_day": notImplemented("best_day"),
};
