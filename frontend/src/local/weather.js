// Open-Meteo client — port of backend/app/weather.py.
// CapacitorHttp handles the request from native so we don't trip on CORS.

import { CapacitorHttp } from "@capacitor/core";
import * as forecastSettings from "./forecast.js";

const FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
const ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive";
const CACHE_TTL_MS = 15 * 60 * 1000;
const cache = new Map();

async function fetchJson(url, params) {
  // Capacitor's iOS HttpPlugin does a strict cast of every params value to
  // String inside setUrlParams; passing a number crashes the WebView process.
  // Stringify everything before handing it over.
  const stringParams = {};
  for (const [k, v] of Object.entries(params || {})) stringParams[k] = String(v);
  const key = `${url}?${new URLSearchParams(stringParams).toString()}`;
  const cached = cache.get(key);
  if (cached && Date.now() - cached.t < CACHE_TTL_MS) return cached.v;
  const res = await CapacitorHttp.get({ url, params: stringParams });
  if (res.status !== 200) {
    throw new Error(`open-meteo ${url} → HTTP ${res.status}`);
  }
  const v = typeof res.data === "object" ? res.data : JSON.parse(res.data);
  cache.set(key, { t: Date.now(), v });
  return v;
}

export async function forecast(days = 7, pastDays = 0) {
  const s = await forecastSettings.getSettings();
  const params = {
    latitude: s.lat,
    longitude: s.lon,
    hourly: [
      "temperature_2m",
      "relative_humidity_2m",
      "apparent_temperature",
      "cloud_cover",
      "wind_speed_10m",
      "shortwave_radiation",
      "direct_normal_irradiance",
      "diffuse_radiation",
      "precipitation_probability",
    ].join(","),
    current: [
      "temperature_2m",
      "apparent_temperature",
      "relative_humidity_2m",
      "cloud_cover",
      "shortwave_radiation",
      "wind_speed_10m",
    ].join(","),
    daily: [
      "temperature_2m_max",
      "temperature_2m_min",
      "sunrise",
      "sunset",
      "shortwave_radiation_sum",
      "precipitation_sum",
      "uv_index_max",
    ].join(","),
    forecast_days: days,
    timezone: s.tz || "auto",
    wind_speed_unit: "mph",
    temperature_unit: "fahrenheit",
  };
  if (pastDays > 0) params.past_days = pastDays;
  return fetchJson(FORECAST_URL, params);
}

export async function historical(startDate, endDate) {
  const s = await forecastSettings.getSettings();
  return fetchJson(ARCHIVE_URL, {
    latitude: s.lat,
    longitude: s.lon,
    start_date: startDate,
    end_date: endDate,
    hourly: "temperature_2m,relative_humidity_2m,apparent_temperature,cloud_cover,shortwave_radiation,wind_speed_10m",
    timezone: s.tz || "auto",
    wind_speed_unit: "mph",
    temperature_unit: "fahrenheit",
  });
}
