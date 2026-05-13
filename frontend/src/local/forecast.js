// Forecasting / analytics — port of backend/app/forecast.py.
// All math, no I/O beyond the local history and Open-Meteo.

import { history } from "./history.js";
import { clearskyPowerW } from "./solar.js";
import { eg4 } from "./eg4Client.js";
import * as weather from "./weather.js";

const BUCKET_MIN = 15;
const DEFAULTS = {
  lat: 31.025,
  lon: -114.838,
  tz: "America/Tijuana",
  peak_kw: 10.0,
  battery_capacity_kwh: 14.3,
  max_charge_kw: 8.0,
  history_days: 7,
};
const PV_FIELDS = ["ppv", "ppvpCharge", "pPV", "totalPv", "ppv1", "totalPVPower"];
const LOAD_FIELDS = ["consumptionPower", "pLoad", "totalLoad"];
const SOC_FIELDS = ["soc", "batterySoc", "unit0_soc"];

function tzOffsetForName(name) {
  // Look up the current UTC offset for an IANA tz name. Falls back to PDT.
  try {
    const fmt = new Intl.DateTimeFormat("en-US", { timeZone: name, timeZoneName: "shortOffset" });
    const part = fmt.formatToParts(new Date()).find((p) => p.type === "timeZoneName");
    const m = /GMT([+-]?\d+)(?::(\d+))?/.exec(part?.value || "");
    if (!m) return -420;
    const sign = m[1].startsWith("-") ? -1 : 1;
    const h = Math.abs(parseInt(m[1], 10));
    const mi = m[2] ? parseInt(m[2], 10) : 0;
    return sign * (h * 60 + mi);
  } catch {
    return -420;
  }
}

export async function getSettings() {
  const raw = await history.getSettings();
  const out = { ...DEFAULTS };
  for (const [k, v] of Object.entries(raw)) {
    try { out[k] = JSON.parse(v); } catch { out[k] = v; }
  }
  out.tz_offset_minutes = tzOffsetForName(out.tz);
  return out;
}

export async function putSettings(body) {
  const allowed = new Set(Object.keys(DEFAULTS));
  const items = {};
  for (const [k, v] of Object.entries(body || {})) {
    if (allowed.has(k)) items[k] = JSON.stringify(v);
  }
  if (!Object.keys(items).length) {
    throw Object.assign(new Error("no recognized settings"), { status: 400 });
  }
  await history.setSettings(items);
  return getSettings();
}

export async function tzOffsetMinutes() {
  const s = await getSettings();
  return s.tz_offset_minutes;
}

async function pickField(serial, candidates) {
  const known = await history.knownFields(serial);
  for (const f of candidates) if (known.has(f)) return f;
  return null;
}

async function socNow(serial) {
  const known = await history.knownFields(serial);
  const unitFields = [...known].filter((f) => f.endsWith("_soc")).sort();
  const fields = unitFields.length ? unitFields : ["soc", "batterySoc"].filter((f) => known.has(f));
  if (!fields.length) return null;
  const latest = await history.latest(serial, fields);
  const values = Object.values(latest).map((v) => v.value).filter((v) => v != null);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

async function socRatePerMin(serial, windowMin = 30) {
  const known = await history.knownFields(serial);
  const unitFields = [...known].filter((f) => f.endsWith("_soc")).sort();
  const fields = unitFields.length ? unitFields : ["soc", "batterySoc"].filter((f) => known.has(f));
  if (!fields.length) return null;
  const now = Date.now();
  const rates = [];
  for (const f of fields) {
    const pts = await history.query(serial, f, now - windowMin * 60_000, now, 200);
    if (pts.length < 2) continue;
    const dtMin = (pts[pts.length - 1].ts - pts[0].ts) / 60_000;
    if (dtMin <= 0) continue;
    rates.push((pts[pts.length - 1].value - pts[0].value) / dtMin);
  }
  return rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
}

function nowLocal(tzOff) {
  return new Date(Date.now() + tzOff * 60_000);
}

function bucketOfLocal(date) {
  return Math.floor((date.getUTCHours() * 60 + date.getUTCMinutes()) / BUCKET_MIN) * BUCKET_MIN;
}

// ---------------------------------------------------------------------------
// solar_today
// ---------------------------------------------------------------------------
export async function solarToday(serial) {
  const s = await getSettings();
  const tzOff = s.tz_offset_minutes;
  const pvField = await pickField(serial, PV_FIELDS);
  const loadField = await pickField(serial, LOAD_FIELDS);
  const histPv = pvField
    ? await history.bucketAvgByTimeOfDay(serial, pvField, s.history_days, BUCKET_MIN, tzOff)
    : {};
  const histLoad = loadField
    ? await history.bucketAvgByTimeOfDay(serial, loadField, s.history_days, BUCKET_MIN, tzOff)
    : {};

  const now = nowLocal(tzOff);
  const nowBucket = bucketOfLocal(now);

  let todayPv = {};
  if (pvField) {
    const recent = await history.bucketAvgByTimeOfDay(serial, pvField, 1, BUCKET_MIN, tzOff);
    for (const [b, v] of Object.entries(recent)) {
      if (Number(b) <= nowBucket) todayPv[b] = v;
    }
  }

  const buckets = [];
  for (let b = 0; b < 24 * 60; b += BUCKET_MIN) {
    const dt = new Date(now);
    dt.setUTCHours(Math.floor(b / 60), b % 60, 0, 0);
    const clearsky = clearskyPowerW(s.lat, s.lon, dt, s.peak_kw);
    buckets.push({
      minute_of_day: b,
      clearsky_w: clearsky,
      historical_avg_w: histPv[b] ?? null,
      actual_w: b <= nowBucket ? (todayPv[b] ?? null) : null,
      historical_load_w: histLoad[b] ?? null,
    });
  }

  let daysOfHistory = 0;
  if (pvField) {
    const first = await history.firstSampleTs(serial, pvField);
    if (first != null) daysOfHistory = Math.max(1, Math.floor((Date.now() - first) / 86_400_000));
  }

  return {
    tz_offset_minutes: tzOff,
    location: { lat: s.lat, lon: s.lon },
    peak_kw: s.peak_kw,
    pv_field: pvField,
    load_field: loadField,
    bucket_minutes: BUCKET_MIN,
    now_bucket: nowBucket,
    days_of_history: daysOfHistory,
    buckets,
  };
}

// ---------------------------------------------------------------------------
// excess_today (simplified — same shape as backend)
// ---------------------------------------------------------------------------
export async function excessToday(serial) {
  const s = await getSettings();
  const tzOff = s.tz_offset_minutes;
  const pvField = await pickField(serial, PV_FIELDS);
  const loadField = await pickField(serial, LOAD_FIELDS);
  const histPvMax = pvField
    ? await history.bucketMaxByTimeOfDay(serial, pvField, 14, BUCKET_MIN, tzOff)
    : {};
  const histPvAvg = pvField
    ? await history.bucketAvgByTimeOfDay(serial, pvField, 14, BUCKET_MIN, tzOff)
    : {};
  const histLoadAvg = loadField
    ? await history.bucketAvgByTimeOfDay(serial, loadField, 14, BUCKET_MIN, tzOff)
    : {};
  const todayPv = pvField
    ? await history.bucketAvgByTimeOfDay(serial, pvField, 1, BUCKET_MIN, tzOff)
    : {};
  const todayLoad = loadField
    ? await history.bucketAvgByTimeOfDay(serial, loadField, 1, BUCKET_MIN, tzOff)
    : {};

  const now = nowLocal(tzOff);
  const nowBucket = bucketOfLocal(now);
  const buckets = [];
  for (let b = 0; b < 24 * 60; b += BUCKET_MIN) {
    const dt = new Date(now);
    dt.setUTCHours(Math.floor(b / 60), b % 60, 0, 0);
    const clearsky = clearskyPowerW(s.lat, s.lon, dt, s.peak_kw);
    const observedMax = histPvMax[b];
    const expectedMax = observedMax && observedMax > 0 ? Math.min(observedMax, clearsky * 1.05) : clearsky;
    const expectedLoad = histLoadAvg[b] || 0;
    buckets.push({
      minute_of_day: b,
      clearsky_w: clearsky,
      expected_max_w: expectedMax,
      historical_avg_pv_w: histPvAvg[b] ?? null,
      expected_load_w: expectedLoad,
      actual_pv_w: b <= nowBucket ? (todayPv[b] ?? null) : null,
      actual_load_w: b <= nowBucket ? (todayLoad[b] ?? null) : null,
      excess_w: Math.max(0, expectedMax - expectedLoad),
    });
  }

  const bucketHours = BUCKET_MIN / 60;
  const totalExcessKwh = buckets.reduce((a, b) => a + b.excess_w, 0) * bucketHours / 1000;

  return {
    tz_offset_minutes: tzOff,
    location: { lat: s.lat, lon: s.lon },
    peak_kw: s.peak_kw,
    pv_field: pvField,
    load_field: loadField,
    bucket_minutes: BUCKET_MIN,
    now_bucket: nowBucket,
    days_of_history: 0,
    buckets,
    summary: {
      now: buckets[Math.floor(nowBucket / BUCKET_MIN)] || null,
      peak_excess_bucket: buckets.reduce((a, b) => (a && a.excess_w > b.excess_w ? a : b), null),
      total_excess_today_kwh: totalExcessKwh,
    },
  };
}

// ---------------------------------------------------------------------------
// battery_completion + historical_completion
// ---------------------------------------------------------------------------
export async function batteryCompletion(serial) {
  const s = await getSettings();
  const tzOff = s.tz_offset_minutes;
  const curSoc = await socNow(serial);
  if (curSoc == null) return { reason: "no SoC samples yet — let the poller collect data for a few minutes." };
  if (curSoc >= 99.5) return { current_soc_pct: curSoc, reason: "battery already full" };

  const pvField = await pickField(serial, PV_FIELDS);
  const loadField = await pickField(serial, LOAD_FIELDS);
  const histPv = pvField
    ? await history.bucketAvgByTimeOfDay(serial, pvField, s.history_days, BUCKET_MIN, tzOff)
    : null;
  const histLoad = loadField
    ? await history.bucketAvgByTimeOfDay(serial, loadField, s.history_days, BUCKET_MIN, tzOff)
    : null;
  const measuredRate = await socRatePerMin(serial);
  if ((!histPv && measuredRate == null) || (measuredRate != null && measuredRate <= 0 && !histPv)) {
    return {
      current_soc_pct: curSoc,
      measured_rate_pct_per_min: measuredRate,
      reason: "not currently charging and no historical solar curve yet",
    };
  }

  const stepMin = 5;
  const horizon = 12 * 60;
  const now = nowLocal(tzOff);
  let soc = curSoc;
  const projection = [{ ts: Date.now(), soc_pct: soc }];
  let etaUtcMs = null;

  for (let step = 1; step <= horizon / stepMin; step++) {
    const t = new Date(now.getTime() + step * stepMin * 60_000);
    const b = Math.floor((t.getUTCHours() * 60 + t.getUTCMinutes()) / BUCKET_MIN) * BUCKET_MIN;
    let pvW = 0;
    if (histPv) pvW = histPv[b] || 0;
    else pvW = clearskyPowerW(s.lat, s.lon, t, s.peak_kw) * 0.6;
    const loadW = histLoad ? (histLoad[b] || 0) : 0;
    let netW = pvW - loadW;
    netW = Math.max(-s.max_charge_kw * 1000, Math.min(s.max_charge_kw * 1000, netW));
    let deltaPct;
    if (!histPv && measuredRate != null) deltaPct = measuredRate * stepMin;
    else deltaPct = (netW * (stepMin / 60) / 1000) / s.battery_capacity_kwh * 100;
    soc = Math.max(0, Math.min(100, soc + deltaPct));
    const tsUtc = Date.now() + step * stepMin * 60_000;
    projection.push({ ts: tsUtc, soc_pct: Math.round(soc * 100) / 100 });
    if (soc >= 100 && etaUtcMs == null) {
      etaUtcMs = tsUtc;
      break;
    }
  }

  const historical = await historicalCompletion(serial, curSoc, s);

  return {
    current_soc_pct: Math.round(curSoc * 100) / 100,
    measured_rate_pct_per_min: measuredRate,
    eta_iso: etaUtcMs ? new Date(etaUtcMs).toISOString() : null,
    minutes_remaining: etaUtcMs ? Math.round((etaUtcMs - Date.now()) / 60_000) : null,
    battery_capacity_kwh: s.battery_capacity_kwh,
    max_charge_kw: s.max_charge_kw,
    step_minutes: stepMin,
    projection,
    used_historical: !!histPv,
    historical_eta: historical,
  };
}

async function historicalCompletion(serial, currentSoc, s, days = 7, tolerance = 2.0, fullThreshold = 99.0) {
  const tzOff = s.tz_offset_minutes;
  const socField = await pickField(serial, SOC_FIELDS);
  if (!socField) return { matches: [], median_minutes_to_full: null, eta_iso: null, matched_days: 0, considered_days: 0, reason: "no SoC field" };
  const todayLocal = nowLocal(tzOff);
  const matches = [];
  for (let back = 1; back <= days; back++) {
    const d = new Date(todayLocal);
    d.setUTCDate(d.getUTCDate() - back);
    d.setUTCHours(0, 0, 0, 0);
    const startMs = d.getTime() - tzOff * 60_000;
    const endMs = startMs + 42 * 3_600_000;
    const pts = await history.query(serial, socField, startMs, endMs, 240);
    if (pts.length < 10) continue;
    let minIdx = 0;
    for (let i = 1; i < pts.length; i++) if (pts[i].value < pts[minIdx].value) minIdx = i;
    let matchIdx = null;
    for (let i = minIdx; i < pts.length; i++) {
      if (Math.abs(pts[i].value - currentSoc) <= tolerance) { matchIdx = i; break; }
    }
    if (matchIdx == null) continue;
    const horizonMs = pts[matchIdx].ts + 8 * 3_600_000;
    let fullIdx = null;
    for (let i = matchIdx; i < pts.length; i++) {
      if (pts[i].ts > horizonMs) break;
      if (pts[i].value >= fullThreshold) { fullIdx = i; break; }
    }
    if (fullIdx == null) continue;
    const elapsedMin = (pts[fullIdx].ts - pts[matchIdx].ts) / 60_000;
    const fmt = (ms) => {
      const x = new Date(ms + tzOff * 60_000);
      return `${String(x.getUTCHours()).padStart(2, "0")}:${String(x.getUTCMinutes()).padStart(2, "0")}`;
    };
    matches.push({
      date: d.toISOString().slice(0, 10),
      matched_at_local: fmt(pts[matchIdx].ts),
      matched_soc: Math.round(pts[matchIdx].value * 10) / 10,
      full_at_local: fmt(pts[fullIdx].ts),
      elapsed_minutes: Math.round(elapsedMin * 10) / 10,
    });
  }
  if (!matches.length) {
    return { matches: [], median_minutes_to_full: null, eta_iso: null, matched_days: 0, considered_days: days, reason: `no past day matched ${currentSoc.toFixed(0)}%` };
  }
  const elapsed = matches.map((m) => m.elapsed_minutes).sort((a, b) => a - b);
  const median = elapsed.length % 2 ? elapsed[(elapsed.length - 1) / 2] : (elapsed[elapsed.length / 2 - 1] + elapsed[elapsed.length / 2]) / 2;
  return {
    matches,
    matched_days: matches.length,
    considered_days: days,
    median_minutes_to_full: Math.round(median * 10) / 10,
    min_minutes_to_full: Math.min(...elapsed),
    max_minutes_to_full: Math.max(...elapsed),
    eta_iso: new Date(Date.now() + median * 60_000).toISOString(),
  };
}

// ---------------------------------------------------------------------------
// max_production envelope (clear-sky for one local day)
// ---------------------------------------------------------------------------
export async function maxProduction() {
  const s = await getSettings();
  const now = nowLocal(s.tz_offset_minutes);
  const midnight = new Date(now);
  midnight.setUTCHours(0, 0, 0, 0);
  const buckets = [];
  for (let b = 0; b < 24 * 60; b += BUCKET_MIN) {
    const t = new Date(midnight.getTime() + b * 60_000);
    buckets.push({ minute_of_day: b, clearsky_w: clearskyPowerW(s.lat, s.lon, t, s.peak_kw) });
  }
  return { tz_offset_minutes: s.tz_offset_minutes, location: { lat: s.lat, lon: s.lon }, peak_kw: s.peak_kw, bucket_minutes: BUCKET_MIN, buckets };
}

// ---------------------------------------------------------------------------
// tomorrow forecast (PV + load) — coarse version, no AC model
// ---------------------------------------------------------------------------
export async function tomorrow(serial, horizonDays = 2) {
  const s = await getSettings();
  const wx = await weather.forecast(horizonDays);
  const h = wx.hourly || {};
  const times = h.time || [];
  const ghi = h.shortwave_radiation || [];
  const temps = h.temperature_2m || [];
  const cloud = h.cloud_cover || [];
  const peakGhi = Math.max(...ghi.slice(0, 48), 0);
  const pvPerGhi = peakGhi > 0 ? (s.peak_kw * 1000 * 0.8) / 1000 : 0;
  const rows = times.map((t, i) => {
    const tempF = temps[i] ?? null;
    const cloudPct = cloud[i] ?? null;
    const ghiW = ghi[i] || 0;
    const predPv = ghiW * pvPerGhi;
    return {
      time: t,
      hour_of_day: parseInt(t.slice(11, 13), 10),
      temperature_f: tempF,
      cloud_pct: cloudPct,
      ghi_wm2: ghiW,
      predicted_pv_w: predPv,
      predicted_load_w: null,
      predicted_ac_w: null,
      predicted_base_load_w: null,
      predicted_surplus_w: predPv,
    };
  });
  return {
    serial,
    tz: s.tz,
    location: { lat: s.lat, lon: s.lon },
    ac_model: { threshold_f: null, slope_w_per_f: null, r_squared: null, days_used: 0, load_field: null },
    pv_calibration: { field: "ppv", w_per_ghi: pvPerGhi },
    hourly: rows,
  };
}

// ---------------------------------------------------------------------------
// daychart + range + aggregate + heatmap + string_health
// ---------------------------------------------------------------------------
export async function dayChart(query) {
  const s = await getSettings();
  const tzOff = s.tz_offset_minutes;
  const [y, mo, d] = query.date.split("-").map(Number);
  const dayStart = new Date(Date.UTC(y, mo - 1, d, 0, 0, 0)) - tzOff * 60_000;
  const dayEnd = dayStart + 86_400_000;
  const known = await history.knownFields(query.serial);
  const fields = ["ppv", "consumptionPower", "pCharge", "pDisCharge", "gridPower", "soc", "acCouplePower"].filter((f) => known.has(f));
  const series = {};
  for (const f of fields) {
    series[f] = await history.query(query.serial, f, dayStart, dayEnd, 200);
  }
  return {
    serial: query.serial,
    date: query.date,
    tz_offset_minutes: tzOff,
    start_ms: dayStart,
    end_ms: dayEnd,
    series,
  };
}

export async function rangeQuery(query) {
  const now = Date.now();
  const end = Number(query.end) || now;
  const days = query.days ? Number(query.days) : null;
  const start = Number(query.start) || (days != null ? end - days * 86_400_000 : end - 7 * 86_400_000);
  if (start >= end) throw Object.assign(new Error("start must be < end"), { status: 400 });
  const span = end - start;
  const targetPoints = Number(query.target_points) || 400;
  const idealBucket = Math.max(60_000, Math.floor(span / targetPoints));
  const SNAPS = [
    ["1m", 60_000], ["5m", 5 * 60_000], ["15m", 15 * 60_000],
    ["1h", 60 * 60_000], ["6h", 6 * 60 * 60_000], ["1d", 24 * 60 * 60_000],
  ];
  let [label, bucketMs] = SNAPS[SNAPS.length - 1];
  for (const [lab, ms] of SNAPS) {
    if (ms >= idealBucket) { label = lab; bucketMs = ms; break; }
  }
  const fields = (query.fields || "ppv,consumptionPower,pCharge,pDisCharge,pToGrid,pToUser,peps,soc").split(",").map((x) => x.trim()).filter(Boolean);
  const series = {};
  for (const f of fields) {
    series[f] = await history.query(query.serial, f, start, end, Math.ceil(span / bucketMs));
  }
  return { serial: query.serial, start_ms: start, end_ms: end, span_ms: span, bucket_ms: bucketMs, bucket_label: label, fields, series };
}

export async function aggregate(query) {
  const s = await getSettings();
  const now = Date.now();
  const end = Number(query.end) || now;
  let start = Number(query.start);
  if (!start) {
    start = query.days ? end - Number(query.days) * 86_400_000 : end - 7 * 86_400_000;
  }
  const rows = await history.aggregate(query.serial, query.field, start, end, query.group_by || "day", query.fn || "avg", s.tz_offset_minutes);
  return { serial: query.serial, field: query.field, start_ms: start, end_ms: end, group_by: query.group_by || "day", fn: query.fn || "avg", tz_offset_minutes: s.tz_offset_minutes, rows };
}

export async function heatmap(query) {
  const s = await getSettings();
  const now = Date.now();
  const days = Number(query.days) || 365;
  const rows = await history.aggregate(query.serial, query.field || "ppv", now - days * 86_400_000, now, "day", "avg", s.tz_offset_minutes);
  const cells = rows.filter((r) => r.value != null).map((r) => ({ date: r.bucket, kwh: r.value * 24 / 1000, samples: r.count }));
  return { serial: query.serial, field: query.field || "ppv", days_window: days, cells };
}

export async function stringHealth(query) {
  const s = await getSettings();
  const now = Date.now();
  const days = Number(query.days) || 7;
  const start = now - days * 86_400_000;
  const known = await history.knownFields(query.serial);
  const strings = [...known].filter((f) => /^ppv[1-9]$/.test(f)).sort();
  if (!strings.length) return { serial: query.serial, strings: [], note: "no per-string PV fields" };
  const series = {};
  for (const ss of strings) {
    const rows = await history.aggregate(query.serial, ss, start, now, "day", "avg", s.tz_offset_minutes);
    series[ss] = rows.filter((r) => r.value != null).map((r) => ({ date: r.bucket, avg_w: r.value }));
  }
  const daysSeen = [...new Set(Object.values(series).flat().map((d) => d.date))].sort();
  const health = [];
  for (const day of daysSeen) {
    const byS = {};
    for (const ss of strings) byS[ss] = (series[ss].find((d) => d.date === day) || {}).avg_w ?? null;
    const values = Object.values(byS).filter((v) => v);
    if (!values.length) continue;
    const maxV = Math.max(...values);
    const deviations = {};
    for (const ss of strings) deviations[ss] = byS[ss] != null && maxV ? (byS[ss] / maxV) : null;
    health.push({ date: day, values: byS, ratio_to_strongest: deviations });
  }
  return { serial: query.serial, strings, series, health };
}

// Actual daily PV kWh vs irradiance-expected daily kWh, for a degradation trend.
// Mirrors backend/app/main.py `/api/performance`.
export async function performance(query) {
  const s = await getSettings();
  const serial = query.serial;
  const days = Math.max(1, Number(query.days) || 30);
  const now = Date.now();
  const start = now - days * 86_400_000;
  const pvRows = await history.aggregate(
    serial, "ppv", start, now, "day", "avg", s.tz_offset_minutes,
  );
  const today = new Date(now + s.tz_offset_minutes * 60_000).toISOString().slice(0, 10);
  const startDate = new Date(now - days * 86_400_000 + s.tz_offset_minutes * 60_000).toISOString().slice(0, 10);
  let arch;
  try {
    arch = await weather.historical(startDate, today);
  } catch (ex) {
    return { serial, error: `weather archive failed: ${ex.message}` };
  }
  const hourly = arch.hourly || {};
  const times = hourly.time || [];
  const ghis = hourly.shortwave_radiation || [];
  const ghiDaily = {};
  for (let i = 0; i < times.length; i++) {
    const g = ghis[i];
    if (g == null) continue;
    const day = String(times[i]).slice(0, 10);
    ghiDaily[day] = (ghiDaily[day] || 0) + Number(g);
  }
  const rows = pvRows.map((r) => {
    const actual = (r.value || 0) * 24 / 1000; // avg-W → daily kWh estimate
    const expected = (ghiDaily[r.bucket] || 0) * s.peak_kw * 0.8 / 1000;
    const ratio = expected > 0 ? actual / expected : null;
    return { date: r.bucket, actual_kwh: actual, expected_kwh: expected, ratio };
  });
  return { serial, days, rows };
}

// ---------------------------------------------------------------------------
// battery_cycles (the recently-added panel)
// ---------------------------------------------------------------------------
function analyzeDayCycle(pts, dayStartMs, dayEndMs, capacityKwh) {
  if (!pts || pts.length < 5) return null;
  const values = pts.map((p) => p.value);
  const ts = pts.map((p) => p.ts);
  const inDay = [];
  for (let i = 0; i < ts.length; i++) if (ts[i] >= dayStartMs && ts[i] < dayEndMs) inDay.push(i);
  if (!inDay.length) return null;
  let peakIdx = inDay[0];
  for (const i of inDay) if (values[i] > values[peakIdx]) peakIdx = i;
  const peakVal = values[peakIdx];
  let lastAtPeak = peakIdx;
  for (const i of inDay) if (values[i] >= peakVal - 0.5 && i > lastAtPeak) lastAtPeak = i;
  const lookEnd = ts[lastAtPeak] + 24 * 3_600_000;
  const after = [];
  for (let i = lastAtPeak; i < ts.length && ts[i] <= lookEnd; i++) after.push(i);
  let minIdx;
  if (after.length < 2) {
    minIdx = inDay[0];
    for (const i of inDay) if (values[i] < values[minIdx]) minIdx = i;
  } else {
    minIdx = after[0];
    for (const i of after) if (values[i] < values[minIdx]) minIdx = i;
  }
  const minVal = values[minIdx];
  const dropPct = Math.max(0, peakVal - minVal);
  let drainStartIdx = null, chargeStartIdx = null, fullIdx = null;
  if (dropPct >= 3 && minIdx > lastAtPeak) {
    for (let i = minIdx - 1; i >= lastAtPeak; i--) {
      if (values[i] >= peakVal - 1.5) { drainStartIdx = i; break; }
    }
    if (drainStartIdx == null) drainStartIdx = lastAtPeak;
    for (let i = minIdx + 1; i < values.length; i++) {
      if (values[i] >= minVal + 2) { chargeStartIdx = i; break; }
    }
    if (chargeStartIdx != null) {
      const target = Math.max(peakVal, 95) - 1;
      for (let i = chargeStartIdx; i < values.length; i++) {
        if (values[i] >= target) { fullIdx = i; break; }
      }
    }
  }
  const at = (i) => (i == null ? [null, null] : [ts[i], values[i]]);
  const [peakTs] = at(lastAtPeak);
  const [minTs] = at(minIdx);
  const [drainTs, drainSoc] = at(drainStartIdx);
  const [chargeTs, chargeSoc] = at(chargeStartIdx);
  const [fullTs, fullVal] = at(fullIdx);
  return {
    peak_ts: peakTs, peak_soc: peakVal,
    min_ts: minTs, min_soc: minVal,
    drain_start_ts: drainTs, drain_start_soc: drainSoc,
    charge_start_ts: chargeTs, charge_start_soc: chargeSoc,
    full_charge_ts: fullTs, full_charge_soc: fullVal,
    drain_pct: Math.round(dropPct * 10) / 10,
    drain_kwh: Math.round(dropPct / 100 * capacityKwh * 100) / 100,
    samples: inDay.length,
  };
}

export async function batteryCycles(serial, days = 14) {
  const s = await getSettings();
  const tzOff = s.tz_offset_minutes;
  const known = await history.knownFields(serial);
  const socField = ["soc", "unit0_soc", "batterySoc"].find((f) => known.has(f));
  if (!socField) {
    return {
      serial, tz_offset_minutes: tzOff, battery_capacity_kwh: s.battery_capacity_kwh,
      soc_field: null, days: [], note: "no SoC field in history",
    };
  }
  const todayLocal = nowLocal(tzOff);
  const tempByDate = {};
  try {
    const wx = await weather.forecast(1, days);
    const daily = wx.daily || {};
    const time = daily.time || [];
    const tmin = daily.temperature_2m_min || [];
    const tmax = daily.temperature_2m_max || [];
    for (let i = 0; i < time.length; i++) {
      tempByDate[time[i]] = { temp_min_f: tmin[i] ?? null, temp_max_f: tmax[i] ?? null };
    }
    const hh = wx.hourly || {};
    const acc = {};
    const hhTime = hh.time || [];
    const hhTemp = hh.temperature_2m || [];
    for (let i = 0; i < hhTime.length; i++) {
      if (hhTemp[i] == null) continue;
      const d = hhTime[i].slice(0, 10);
      (acc[d] ||= []).push(hhTemp[i]);
    }
    for (const d of Object.keys(acc)) {
      const arr = acc[d];
      tempByDate[d] = tempByDate[d] || {};
      tempByDate[d].temp_avg_f = Math.round((arr.reduce((a, b) => a + b, 0) / arr.length) * 10) / 10;
    }
  } catch (e) { /* weather is best-effort */ }

  const out = [];
  for (let back = days - 1; back >= 0; back--) {
    const d = new Date(todayLocal);
    d.setUTCDate(d.getUTCDate() - back);
    d.setUTCHours(0, 0, 0, 0);
    const dateText = d.toISOString().slice(0, 10);
    const startMs = d.getTime() - tzOff * 60_000;
    const endMs = startMs + 86_400_000;
    const lookEndMs = startMs + 42 * 3_600_000;
    const pts = await history.query(serial, socField, startMs, lookEndMs, 240);
    const analysis = pts.length ? analyzeDayCycle(pts, startMs, endMs, s.battery_capacity_kwh) : null;
    const t = tempByDate[dateText] || {};
    out.push({
      date: dateText,
      start_ms: startMs,
      end_ms: endMs,
      ...(analysis || { samples: pts.length }),
      temp_min_f: t.temp_min_f ?? null,
      temp_max_f: t.temp_max_f ?? null,
      temp_avg_f: t.temp_avg_f ?? null,
    });
  }
  return {
    serial,
    tz_offset_minutes: tzOff,
    battery_capacity_kwh: s.battery_capacity_kwh,
    soc_field: socField,
    days: out,
  };
}
