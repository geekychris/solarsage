import React, { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";
import { useChartZoom } from "./useChartZoom.js";

function fmtTimeOfDay(ts) {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtETA(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString([], { hour: "2-digit", minute: "2-digit", weekday: "short" });
}

function fmtDuration(min) {
  if (min == null) return "—";
  if (min < 60) return `${min}m`;
  return `${Math.floor(min / 60)}h ${min % 60}m`;
}

export default function BatteryForecast({ serial }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const zoom = useChartZoom({ minSpan: 60_000 });

  useEffect(() => {
    if (!serial) return;
    let cancelled = false;
    async function load() {
      try {
        const r = await api.batteryCompletion(serial);
        if (!cancelled) {
          setData(r);
          setErr("");
        }
      } catch (ex) {
        if (!cancelled) setErr(ex.message);
      }
    }
    load();
    const id = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [serial]);

  if (err) return <div className="panel"><div className="error">{err}</div></div>;
  if (!data) return null;

  // Merge all three projections onto a shared ts axis so recharts
  // can plot them as separate lines.
  const primary = data.projection || [];
  const nowSeries = data.now_rate_projection?.series || [];
  const wxSeries = data.weather_projection?.series || [];
  const byTs = new Map();
  for (const p of primary) {
    byTs.set(p.ts, { ts: p.ts, soc: p.soc_pct });
  }
  for (const p of nowSeries) {
    const row = byTs.get(p.ts) || { ts: p.ts };
    row.now_soc = p.soc_pct;
    byTs.set(p.ts, row);
  }
  for (const p of wxSeries) {
    const row = byTs.get(p.ts) || { ts: p.ts };
    row.wx_soc = p.soc_pct;
    byTs.set(p.ts, row);
  }
  const rows = Array.from(byTs.values()).sort((a, b) => a.ts - b.ts);

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Battery charge forecast</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          {data.used_historical
            ? "based on historical solar curve"
            : data.measured_rate_pct_per_min != null
            ? "based on current charge rate"
            : ""}
        </div>
      </div>

      <div className="forecast-tiles">
        <div className="forecast-tile">
          <div className="label">Current SoC</div>
          <div className="value">{data.current_soc_pct ?? "—"}<span className="unit">%</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Charge rate (now)</div>
          <div className="value">
            {data.measured_rate_pct_per_min != null
              ? (data.measured_rate_pct_per_min * 60).toFixed(1)
              : "—"}
            <span className="unit">%/h</span>
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">At current W</div>
          <div className="value" style={{ fontSize: 18 }}>
            {fmtETA(data.now_rate_projection?.eta_iso)}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            {data.now_rate_projection?.minutes_remaining != null
              ? `in ${fmtDuration(data.now_rate_projection.minutes_remaining)} · flat @ ${data.now_rate_projection.rate_kw} kW`
              : "not charging"}
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">Weather-aware</div>
          <div className="value" style={{ fontSize: 18 }}>
            {fmtETA(data.weather_projection?.eta_iso)}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            {data.weather_projection?.minutes_remaining != null
              ? `in ${fmtDuration(data.weather_projection.minutes_remaining)} · GHI × ${data.weather_projection.pv_per_ghi_w_per_wm2}`
              : (data.weather_projection ? "won't hit 100% in 12h" : "unavailable")}
          </div>
        </div>
      </div>
      <details style={{ marginTop: 6 }}>
        <summary className="muted" style={{ fontSize: 12, cursor: "pointer" }}>
          More: historical-median ETA + past-day matches
        </summary>
        <div className="forecast-tiles" style={{ marginTop: 8 }}>
          <div className="forecast-tile">
            <div className="label">Model ETA</div>
            <div className="value" style={{ fontSize: 18 }}>{fmtETA(data.eta_iso)}</div>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              in {fmtDuration(data.minutes_remaining)} · {data.used_historical ? "hist curve" : "rate × time"}
            </div>
          </div>
          <div className="forecast-tile">
            <div className="label">Historical median</div>
            <div className="value" style={{ fontSize: 18 }}>
              {fmtETA(data.historical_eta?.eta_iso)}
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              {data.historical_eta?.matched_days > 0
                ? `in ${fmtDuration(data.historical_eta.median_minutes_to_full)} (median of ${data.historical_eta.matched_days})`
                : "no past day matched"}
            </div>
          </div>
        </div>
      </details>

      {data.historical_eta?.matches?.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary className="muted" style={{ fontSize: 12, cursor: "pointer" }}>
            Show how today's SoC matched past days
          </summary>
          <table className="kv-table" style={{ marginTop: 6 }}>
            <thead>
              <tr>
                <td>Day</td>
                <td>Matched SoC at</td>
                <td>Reached 100% at</td>
                <td>Elapsed</td>
              </tr>
            </thead>
            <tbody>
              {data.historical_eta.matches.map((m) => (
                <tr key={m.date}>
                  <td>{m.date}</td>
                  <td>{m.matched_soc}% @ {m.matched_at_local}</td>
                  <td>{m.full_at_local}</td>
                  <td>{fmtDuration(Math.round(m.elapsed_minutes))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {data.reason && (
        <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{data.reason}</div>
      )}
      {data.historical_eta?.reason && !data.historical_eta?.matched_days && (
        <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>
          Historical ETA: {data.historical_eta.reason}
        </div>
      )}

      {rows.length > 0 && (
        <>
          {zoom.isZoomed && (
            <button onClick={zoom.reset} style={{ marginTop: 6 }}>Reset zoom</button>
          )}
          <div className="chart-wrap" style={{ height: 260, marginTop: 12, userSelect: "none" }}>
            <ResponsiveContainer>
              <LineChart
                data={rows}
                margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
                {...zoom.chartProps}
              >
                <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
                <XAxis
                  dataKey="ts"
                  type="number"
                  domain={zoom.domain}
                  allowDataOverflow
                  scale="time"
                  stroke="#8b97a8"
                  tick={{ fill: "#8b97a8", fontSize: 11 }}
                  tickFormatter={fmtTimeOfDay}
                  minTickGap={40}
                />
                <YAxis
                  stroke="#8b97a8"
                  domain={[0, 100]}
                  tick={{ fill: "#8b97a8", fontSize: 11 }}
                  label={{ value: "SoC %", angle: -90, position: "insideLeft", fill: "#8b97a8", fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
                  labelStyle={{ color: "#8b97a8" }}
                  labelFormatter={fmtTimeOfDay}
                />
                <ReferenceLine y={100} stroke="#2ea043" strokeDasharray="3 3" />
                <Legend
                  verticalAlign="top"
                  height={24}
                  wrapperStyle={{ fontSize: 11, color: "#8b97a8" }}
                />
                {zoom.refArea && (
                  <ReferenceArea x1={zoom.refArea.x1} x2={zoom.refArea.x2} fill="#58a6ff" fillOpacity={0.15} />
                )}
                {zoom.crosshairs.map((p) => (
                  <ReferenceLine
                    key={`xh-${p.dataKey}`}
                    y={p.value}
                    stroke={p.color}
                    strokeDasharray="2 3"
                    strokeOpacity={0.55}
                    ifOverflow="extendDomain"
                  />
                ))}
                <Line
                  type="monotone"
                  dataKey="wx_soc"
                  stroke="#3fb950"
                  strokeWidth={3}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                  name="Weather-aware"
                />
                <Line
                  type="monotone"
                  dataKey="now_soc"
                  stroke="#d29922"
                  strokeWidth={2}
                  strokeDasharray="4 3"
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                  name="At current W"
                />
                <Line
                  type="monotone"
                  dataKey="soc"
                  stroke="#58a6ff"
                  strokeWidth={2}
                  strokeOpacity={0.5}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                  name="Model (hist curve)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
