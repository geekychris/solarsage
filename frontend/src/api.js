const TOKEN_KEY = "eg4.token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

// Capacitor detection — same React bundle ships to the web (FastAPI backend)
// and to iOS/Android (in-app handlers). Inside Capacitor the app is served from
// capacitor://localhost (iOS) or http://localhost (Android), so we route /api/*
// calls to local handlers instead of HTTP.
const IS_NATIVE = (() => {
  if (typeof window === "undefined") return false;
  const cap = window.Capacitor;
  return !!(cap && cap.isNativePlatform && cap.isNativePlatform());
})();

let localHandlersPromise = null;
async function getLocalHandlers() {
  if (!localHandlersPromise) {
    // Dynamic import keeps the local stack out of the web bundle.
    localHandlersPromise = import("./local/server.js").then((m) => m.handlers);
  }
  return localHandlersPromise;
}

async function dispatchLocal(path, opts) {
  const handlers = await getLocalHandlers();
  const url = new URL(path, "http://local");
  const route = `${opts.method || "GET"} ${url.pathname}`;
  const handler = handlers[route];
  if (!handler) {
    const err = new Error(`No local handler for ${route}`);
    err.status = 404;
    throw err;
  }
  return await handler({
    query: Object.fromEntries(url.searchParams),
    body: opts.body,
  });
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  if (IS_NATIVE) return dispatchLocal(path, { method, body });

  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    const msg = data?.detail || res.statusText || "request failed";
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

function safeJson(t) {
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
}

export const api = {
  login: (username, password, remember = false) =>
    request("/api/login", {
      method: "POST",
      body: { username, password, remember },
      auth: false,
    }),
  logout: (forget = false) =>
    request(`/api/logout${forget ? "?forget=true" : ""}`, { method: "POST" }),
  authStatus: () => request("/api/auth/status", { auth: false }),
  useSaved: () => request("/api/auth/use_saved", { method: "POST", auth: false }),
  inverters: () => request("/api/inverters"),
  snapshot: (serial) => request(`/api/snapshot?serial=${encodeURIComponent(serial)}`),
  runtime: (serial) => request(`/api/runtime?serial=${encodeURIComponent(serial)}`),
  energy: (serial) => request(`/api/energy?serial=${encodeURIComponent(serial)}`),
  battery: (serial) => request(`/api/battery?serial=${encodeURIComponent(serial)}`),
  metrics: (serial) => request(`/api/metrics?serial=${encodeURIComponent(serial)}`),
  history: (serial, field, rangeMinutes, maxPoints = 1000) =>
    request(
      `/api/history?serial=${encodeURIComponent(serial)}&field=${encodeURIComponent(
        field
      )}&range_minutes=${rangeMinutes}&max_points=${maxPoints}`
    ),
  settings: () => request("/api/settings"),
  updateSettings: (body) => request("/api/settings", { method: "PUT", body }),
  solarToday: (serial) =>
    request(`/api/forecast/solar_today?serial=${encodeURIComponent(serial)}`),
  batteryCompletion: (serial) =>
    request(`/api/forecast/battery_completion?serial=${encodeURIComponent(serial)}`),
  maxProduction: () => request("/api/forecast/max_production"),
  excess: (serial) =>
    request(`/api/forecast/excess?serial=${encodeURIComponent(serial)}`),
  weather: (days = 7) => request(`/api/weather?days=${days}`),
  tomorrow: (serial, horizon = 2) =>
    request(
      `/api/forecast/tomorrow?serial=${encodeURIComponent(serial)}&horizon_days=${horizon}`
    ),
  // Multi-site
  listSites: () => request("/api/sites"),
  upsertSite: (body) => request("/api/sites", { method: "POST", body }),
  deleteSite: (id, cascade = false) =>
    request(`/api/sites/${encodeURIComponent(id)}?cascade=${cascade}`, { method: "DELETE" }),
  // Appliances
  listAppliances: (siteId) =>
    request(`/api/appliances?site_id=${encodeURIComponent(siteId)}`),
  upsertAppliance: (body) =>
    request("/api/appliances", { method: "POST", body }),
  deleteAppliance: (id, siteId) =>
    request(`/api/appliances/${id}?site_id=${encodeURIComponent(siteId)}`, { method: "DELETE" }),
  // Scheduler
  schedule: (serial, siteId) =>
    request(
      `/api/schedule?serial=${encodeURIComponent(serial)}&site_id=${encodeURIComponent(siteId)}`
    ),
  // Heatmap / health / performance
  heatmap: (serial, days = 365, field = "ppv") =>
    request(
      `/api/heatmap?serial=${encodeURIComponent(serial)}&days=${days}&field=${field}`
    ),
  stringHealth: (serial, days = 7) =>
    request(
      `/api/string_health?serial=${encodeURIComponent(serial)}&days=${days}`
    ),
  performance: (serial, days = 30) =>
    request(
      `/api/performance?serial=${encodeURIComponent(serial)}&days=${days}`
    ),
  // Alerts
  listAlerts: (siteId, unack = false) =>
    request(
      `/api/alerts?site_id=${encodeURIComponent(siteId)}&unacknowledged_only=${unack}`
    ),
  ackAlert: (id) => request(`/api/alerts/${id}/ack`, { method: "POST" }),
  // Export
  exportCsvUrl: (serial, field, start, end) =>
    `/api/export.csv?serial=${encodeURIComponent(serial)}&field=${encodeURIComponent(field)}&start=${start}&end=${end}&api_key=${encodeURIComponent("local-dev-key-change-me")}`,
  dayChart: (serial, date) =>
    request(
      `/api/daychart?serial=${encodeURIComponent(serial)}&date=${encodeURIComponent(date)}`
    ),
  range: (serial, { start, end, days, fields, targetPoints = 400 } = {}) => {
    const p = new URLSearchParams({ serial });
    if (start != null) p.set("start", String(start));
    if (end != null) p.set("end", String(end));
    if (days != null) p.set("days", String(days));
    if (fields) p.set("fields", fields);
    p.set("target_points", String(targetPoints));
    return request(`/api/range?${p.toString()}`);
  },
  backfill: (serial, days) =>
    request(`/api/backfill?serial=${encodeURIComponent(serial)}&days=${days}`, {
      method: "POST",
    }),
  coverage: (serial) =>
    request(`/api/coverage?serial=${encodeURIComponent(serial)}`),
  sync: (serial, days = 30) =>
    request(`/api/sync?serial=${encodeURIComponent(serial)}&days=${days}`, {
      method: "POST",
    }),
  diagnostic: (serial) =>
    request(`/api/diagnostic?serial=${encodeURIComponent(serial)}`),
  summary: (serial, days = 30) =>
    request(`/api/summary?serial=${encodeURIComponent(serial)}&days=${days}`),
  batteryCycles: (serial, days = 14) =>
    request(
      `/api/battery_cycles?serial=${encodeURIComponent(serial)}&days=${days}`
    ),
};
