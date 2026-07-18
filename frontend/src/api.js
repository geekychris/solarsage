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
  const method = opts.method || "GET";
  const route = `${method} ${url.pathname}`;
  let handler = handlers[route];
  let params = {};
  if (!handler) {
    // Fall back to pattern routes ("DELETE /api/appliances/:id"). Keep this
    // path off the hot list — exact-match wins on every request.
    for (const key of Object.keys(handlers)) {
      if (!key.includes(":")) continue;
      const spaceIdx = key.indexOf(" ");
      if (key.slice(0, spaceIdx) !== method) continue;
      const names = [];
      const pattern = key.slice(spaceIdx + 1).replace(/:([A-Za-z_][A-Za-z0-9_]*)/g, (_, n) => {
        names.push(n);
        return "([^/]+)";
      });
      const m = url.pathname.match(new RegExp(`^${pattern}$`));
      if (m) {
        handler = handlers[key];
        names.forEach((n, i) => (params[n] = decodeURIComponent(m[i + 1])));
        break;
      }
    }
  }
  if (!handler) {
    const err = new Error(`No local handler for ${route}`);
    err.status = 404;
    throw err;
  }
  return await handler({
    query: Object.fromEntries(url.searchParams),
    params,
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
  // Network connectivity monitor
  networkStatus: () => request("/api/network/status"),
  networkHistory: (hours = 24) =>
    request(`/api/network/history?hours=${hours}`),
  networkOutages: (limit = 100) =>
    request(`/api/network/outages?limit=${limit}`),
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
  // Widgets (Local tab)
  listWidgets: () => request("/api/widgets"),
  getWidget: (id) => request(`/api/widgets/${encodeURIComponent(id)}`),
  getWidgetConfig: (id) =>
    request(`/api/widgets/${encodeURIComponent(id)}/config`),
  putWidgetConfig: (id, body) =>
    request(`/api/widgets/${encodeURIComponent(id)}/config`, {
      method: "PUT",
      body,
    }),
  refreshWidget: (id) =>
    request(`/api/widgets/${encodeURIComponent(id)}/refresh`, {
      method: "POST",
    }),
  // Events / reminders
  eventsToday: () => request("/api/events/today"),
  eventsUpcoming: (days = 2) => request(`/api/events/upcoming?days=${days}`),
  listEvents: (params = {}) => {
    const p = new URLSearchParams();
    if (params.starts_after) p.set("starts_after", params.starts_after);
    if (params.starts_before) p.set("starts_before", params.starts_before);
    if (params.today_only) p.set("today_only", "true");
    const q = p.toString();
    return request(`/api/events${q ? `?${q}` : ""}`);
  },
  createEvent: (body) => request("/api/events", { method: "POST", body }),
  updateEvent: (id, body) =>
    request(`/api/events/${encodeURIComponent(id)}`, { method: "PUT", body }),
  deleteEvent: (id) =>
    request(`/api/events/${encodeURIComponent(id)}`, { method: "DELETE" }),
  setEventReminders: (id, reminders) =>
    request(`/api/events/${encodeURIComponent(id)}/reminders`, {
      method: "PUT",
      body: { reminders },
    }),
  testSayEvent: (id) =>
    request(`/api/events/${encodeURIComponent(id)}/say`, { method: "POST" }),
  ingestHoa: () =>
    request("/api/events/ingest_hoa", { method: "POST" }),
  ttsSay: (text) =>
    request("/api/tts/say", { method: "POST", body: { text } }),
  // Translations
  translate: (text, source = "en", target = "es") =>
    request("/api/translations", {
      method: "POST",
      body: { text, source, target },
    }),
  getTranslations: (limit = 50) =>
    request(`/api/translations?limit=${limit}`),
  starTranslation: (id) =>
    request(`/api/translations/${id}/star`, { method: "POST" }),
  deleteTranslation: (id) =>
    request(`/api/translations/${id}`, { method: "DELETE" }),
  // News
  newsHistory: (widgetId, opts = {}) => {
    const p = new URLSearchParams({ widget_id: widgetId });
    if (opts.limit) p.set("limit", String(opts.limit));
    if (opts.translate_to) p.set("translate_to", opts.translate_to);
    return request(`/api/news/history?${p.toString()}`);
  },
  batchTranslateNews: (ids, source = "es", target = "en") =>
    request("/api/news/translate", {
      method: "POST",
      body: { ids, source, target },
    }),
  // Notifications + subscriptions
  notifyTest: (action) =>
    request("/api/notify/test", { method: "POST", body: action }),
  listSubscriptions: () => request("/api/subscriptions"),
  upsertSubscription: (sub) =>
    request("/api/subscriptions", { method: "POST", body: sub }),
  deleteSubscription: (id) =>
    request(`/api/subscriptions/${encodeURIComponent(id)}`, { method: "DELETE" }),
  testSubscription: (id) =>
    request(`/api/subscriptions/${encodeURIComponent(id)}/test`, { method: "POST" }),
  // Rotation mode
  getRotation: () => request("/api/rotation"),
  putRotation: (config) =>
    request("/api/rotation", { method: "PUT", body: config }),
  // Auto-announcements
  getAnnouncements: () => request("/api/announcements"),
  putAnnouncements: (config) =>
    request("/api/announcements", { method: "PUT", body: config }),
  ingestAnnouncements: () =>
    request("/api/announcements/ingest", { method: "POST" }),
  announcementHistory: (limit = 50, minutes = null) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (minutes) qs.set("minutes", String(minutes));
    return request(`/api/announcements/history?${qs}`);
  },
  replayAnnouncements: (minutes = 15, channels = null) => {
    const qs = new URLSearchParams({ minutes: String(minutes) });
    return request(`/api/announcements/replay?${qs}`, {
      method: "POST",
      body: channels ? { channels } : undefined,
    });
  },
  testAnnouncement: (source) =>
    request("/api/announcements/test", {
      method: "POST",
      body: { source },
    }),
  // Property mode — flip HA's input_boolean.house_occupied
  propertyModeSet: (occupied) =>
    request("/api/property_mode/set", {
      method: "POST",
      body: { occupied },
    }),
  // Smart AC override (delegates to Home Assistant). Pass either
  // ``duration_minutes`` (relative window) OR ``until`` (absolute
  // "YYYY-MM-DD HH:MM[:SS]" or ISO). If both are omitted or duration=0,
  // any existing override is cleared and the scheduler resumes control.
  smartAcOverride: ({ room, state, duration_minutes = 0, until }) =>
    request("/api/smart_ac/override", {
      method: "POST",
      body: until ? { room, state, until } : { room, state, duration_minutes },
    }),
  // DAB water-pump control (Sleep / Power-Shower / enable-disable)
  dabPumpControl: ({ action, value }) =>
    request("/api/widgets/dab_pump/control", {
      method: "POST",
      body: value == null ? { action } : { action, value },
    }),
  // HA Integrations
  getHaIntegrations: () => request("/api/ha/integrations"),
  putHaIntegration: (widget_id, body) =>
    request(`/api/ha/integrations/${encodeURIComponent(widget_id)}`, {
      method: "PUT", body,
    }),
  searchHaEntities: (q, domain) => {
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (domain) qs.set("domain", domain);
    return request(`/api/ha/entities?${qs}`);
  },
  // Solar vitals calibration + config
  calibrateSolarVitals: (name, watts) =>
    request("/api/widgets/solar_vitals/calibrate", {
      method: "POST",
      body: { name, watts },
    }),
};
