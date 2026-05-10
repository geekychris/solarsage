import React, { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";

function fmtTemp(f) {
  if (f == null) return "—";
  return `${Math.round(f)}°F`;
}

function shortTime(iso) {
  // "2026-05-11T15:00" → "Mon 15:00" or "15:00" depending on day diff
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toTimeString().slice(0, 5);
  return d.toLocaleString([], { weekday: "short", hour: "2-digit" });
}

export default function WeatherPanel({ serial }) {
  const [w, setW] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const [wx, tm] = await Promise.all([
        api.weather(7),
        api.tomorrow(serial, 2),
      ]);
      setW(wx);
      setForecast(tm);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (!serial) return;
    load();
    const id = setInterval(load, 5 * 60_000); // refresh every 5 min
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial]);

  if (err) return <div className="panel"><div className="error">Weather: {err}</div></div>;
  if (!w || !forecast) return null;

  const c = w.current || {};
  const daily = w.daily || {};
  const hourly = forecast.hourly || [];
  const ac = forecast.ac_model || {};
  const pvCal = forecast.pv_calibration || {};

  // Hourly chart rows for next 48h
  const rows = hourly.slice(0, 48).map((r) => ({
    label: shortTime(r.time),
    Temperature: r.temperature_f != null ? Math.round(r.temperature_f) : null,
    Cloud: r.cloud_pct != null ? Math.round(r.cloud_pct) : null,
    PredictedPV: r.predicted_pv_w != null ? Math.round(r.predicted_pv_w) : null,
    PredictedLoad: r.predicted_load_w != null ? Math.round(r.predicted_load_w) : null,
    AC: r.predicted_ac_w != null ? Math.round(r.predicted_ac_w) : null,
    Surplus: r.predicted_surplus_w != null ? Math.round(r.predicted_surplus_w) : null,
  }));

  // Tomorrow-specific tiles: total kWh of PV, total kWh of AC, surplus
  const tomorrowStart = new Date();
  tomorrowStart.setDate(tomorrowStart.getDate() + 1);
  tomorrowStart.setHours(0, 0, 0, 0);
  const tomorrowEnd = new Date(tomorrowStart);
  tomorrowEnd.setDate(tomorrowEnd.getDate() + 1);
  const tomorrowSlice = hourly.filter((r) => {
    const t = new Date(r.time);
    return t >= tomorrowStart && t < tomorrowEnd;
  });
  const sumKwh = (key) =>
    tomorrowSlice.reduce((s, r) => s + (r[key] || 0), 0) / 1000;
  const tomorrowPvKwh = sumKwh("predicted_pv_w");
  const tomorrowAcKwh = sumKwh("predicted_ac_w");
  const tomorrowLoadKwh = sumKwh("predicted_load_w");
  const tomorrowSurplusKwh = sumKwh("predicted_surplus_w");

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Weather & AC forecast</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          Open-Meteo · {forecast.location?.lat?.toFixed(2)}, {forecast.location?.lon?.toFixed(2)}
        </div>
      </div>

      {/* Current */}
      <div className="forecast-tiles" style={{ marginTop: 10 }}>
        <div className="forecast-tile">
          <div className="label">Outside now</div>
          <div className="value">{fmtTemp(c.temperature_2m)}</div>
          <div className="muted" style={{ fontSize: 11 }}>feels {fmtTemp(c.apparent_temperature)}</div>
        </div>
        <div className="forecast-tile">
          <div className="label">Sky</div>
          <div className="value" style={{ fontSize: 18 }}>{c.cloud_cover ?? "—"}% cloud</div>
          <div className="muted" style={{ fontSize: 11 }}>GHI {Math.round(c.shortwave_radiation || 0)} W/m²</div>
        </div>
        <div className="forecast-tile">
          <div className="label">Humidity / Wind</div>
          <div className="value" style={{ fontSize: 18 }}>{c.relative_humidity_2m}% / {Math.round(c.wind_speed_10m || 0)} mph</div>
        </div>
        <div className="forecast-tile">
          <div className="label">AC model</div>
          <div className="value" style={{ fontSize: 16 }}>
            {ac.slope_w_per_f ? `${Math.round(ac.slope_w_per_f)} W/°F` : "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            above {ac.threshold_f ?? "—"}°F · R²={ac.r_squared?.toFixed(2) ?? "—"} · {ac.days_used ?? 0}d
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">Tomorrow PV</div>
          <div className="value">{tomorrowPvKwh.toFixed(1)}<span className="unit">kWh</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Tomorrow AC load</div>
          <div className="value" style={{ color: "#f85149" }}>
            {tomorrowAcKwh.toFixed(1)}<span className="unit">kWh</span>
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            {tomorrowLoadKwh > 0 ? `${Math.round((tomorrowAcKwh / tomorrowLoadKwh) * 100)}% of total load` : ""}
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">Tomorrow surplus</div>
          <div className="value" style={{ color: tomorrowSurplusKwh > 0 ? "#2ea043" : "#8b97a8" }}>
            {tomorrowSurplusKwh.toFixed(1)}<span className="unit">kWh</span>
          </div>
        </div>
      </div>

      {/* 7-day daily strip */}
      <div className="weekly-strip" style={{ marginTop: 14 }}>
        {(daily.time || []).map((day, i) => (
          <div key={day} className="day-pill">
            <div className="muted" style={{ fontSize: 11 }}>
              {new Date(day).toLocaleDateString([], { weekday: "short" })}
            </div>
            <div style={{ fontWeight: 600 }}>{fmtTemp(daily.temperature_2m_max[i])}</div>
            <div className="muted" style={{ fontSize: 11 }}>
              {fmtTemp(daily.temperature_2m_min[i])}
            </div>
            <div className="muted" style={{ fontSize: 10 }}>
              UV {daily.uv_index_max[i]?.toFixed(1) ?? "—"}
            </div>
          </div>
        ))}
      </div>

      {/* Hourly forecast chart — next 48h */}
      <h4 style={{ margin: "16px 0 6px", fontSize: 13, color: "var(--muted)" }}>
        Next 48 hours
      </h4>
      <div style={{ width: "100%", height: 320 }}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 10, right: 50, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
            <XAxis
              dataKey="label"
              stroke="#8b97a8"
              tick={{ fill: "#8b97a8", fontSize: 11 }}
              interval={Math.max(1, Math.floor(rows.length / 12))}
            />
            <YAxis
              yAxisId="left"
              stroke="#8b97a8"
              tick={{ fill: "#8b97a8", fontSize: 11 }}
              label={{ value: "Watts", angle: -90, position: "insideLeft", fill: "#8b97a8", fontSize: 11 }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              stroke="#8b97a8"
              domain={[40, 120]}
              tick={{ fill: "#8b97a8", fontSize: 11 }}
              label={{ value: "°F", angle: 90, position: "insideRight", fill: "#8b97a8", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
              labelStyle={{ color: "#8b97a8" }}
            />
            <Legend wrapperStyle={{ color: "#8b97a8", fontSize: 12 }} />
            <ReferenceLine y={0} yAxisId="left" stroke="#444" />
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="PredictedPV"
              fill="#2ea043"
              fillOpacity={0.18}
              stroke="#2ea043"
              strokeWidth={2}
              name="Predicted PV"
              isAnimationActive={false}
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="PredictedLoad"
              stroke="#f85149"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Predicted load (incl. AC)"
            />
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="AC"
              stroke="#ff9d76"
              strokeWidth={1.5}
              strokeDasharray="3 3"
              dot={false}
              isAnimationActive={false}
              name="AC contribution"
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="Temperature"
              stroke="#d29922"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Outside °F"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="muted" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.6 }}>
        <strong>How this works:</strong> Open-Meteo provides hourly temperature, cloud cover, and shortwave radiation (GHI) for your location — free, no API key.
        Your <strong>PV calibration</strong> ({pvCal.w_per_ghi?.toFixed(2)} W per W/m² GHI) was derived from <code>{pvCal.field}</code> matched against historical irradiance.
        The <strong>AC model</strong> was fit by regressing historical load against historical outdoor temp at each hour-of-day: base + slope × max(0, temp − threshold).
        Improves as both datasets grow.
      </div>
    </div>
  );
}
