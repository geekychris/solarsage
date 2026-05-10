import React, { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";

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

  const rows = (data.projection || []).map((p) => ({
    ts: p.ts,
    label: new Date(p.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    soc: p.soc_pct,
  }));

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
          <div className="label">Charge rate</div>
          <div className="value">
            {data.measured_rate_pct_per_min != null
              ? (data.measured_rate_pct_per_min * 60).toFixed(1)
              : "—"}
            <span className="unit">%/h</span>
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">100% ETA</div>
          <div className="value" style={{ fontSize: 18 }}>{fmtETA(data.eta_iso)}</div>
        </div>
        <div className="forecast-tile">
          <div className="label">Time remaining</div>
          <div className="value">{fmtDuration(data.minutes_remaining)}</div>
        </div>
      </div>

      {data.reason && (
        <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{data.reason}</div>
      )}

      {rows.length > 0 && (
        <div style={{ width: "100%", height: 260, marginTop: 12 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
              <XAxis dataKey="label" stroke="#8b97a8" tick={{ fill: "#8b97a8", fontSize: 11 }} />
              <YAxis
                stroke="#8b97a8"
                domain={[0, 100]}
                tick={{ fill: "#8b97a8", fontSize: 11 }}
                label={{ value: "SoC %", angle: -90, position: "insideLeft", fill: "#8b97a8", fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
                labelStyle={{ color: "#8b97a8" }}
              />
              <ReferenceLine y={100} stroke="#2ea043" strokeDasharray="3 3" />
              <Line
                type="monotone"
                dataKey="soc"
                stroke="#58a6ff"
                strokeWidth={3}
                dot={false}
                isAnimationActive={false}
                name="Projected SoC"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
