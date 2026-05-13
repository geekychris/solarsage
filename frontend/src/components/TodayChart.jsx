import React, { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";
import { useChartZoom } from "./useChartZoom.js";

function fmtMinute(m) {
  const h = Math.floor(m / 60).toString().padStart(2, "0");
  const mm = (m % 60).toString().padStart(2, "0");
  return `${h}:${mm}`;
}

export default function TodayChart({ serial }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const zoom = useChartZoom({ minSpan: 15 });

  async function load() {
    try {
      const r = await api.solarToday(serial);
      setData(r);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (!serial) return;
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial]);

  if (err) return <div className="panel"><div className="error">{err}</div></div>;
  if (!data) return null;

  const rows = data.buckets.map((b) => ({
    minute: b.minute_of_day,
    label: fmtMinute(b.minute_of_day),
    Actual: b.actual_w == null ? null : Math.round(b.actual_w),
    Historical: b.historical_avg_w == null ? null : Math.round(b.historical_avg_w),
    Clearsky: Math.round(b.clearsky_w),
    Load: b.historical_load_w == null ? null : Math.round(b.historical_load_w),
  }));

  const nowMin = data.now_bucket;
  const today_kwh = data.buckets
    .filter((b) => b.actual_w != null)
    .reduce((s, b) => s + (b.actual_w * (data.bucket_minutes / 60)) / 1000, 0);
  const expected_remaining_kwh = data.buckets
    .filter((b) => b.minute_of_day > nowMin && b.historical_avg_w != null)
    .reduce((s, b) => s + (b.historical_avg_w * (data.bucket_minutes / 60)) / 1000, 0);

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Today's production vs expected</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          {data.days_of_history} days of history · {data.pv_field || "no PV field"}
        </div>
      </div>
      <div className="forecast-tiles">
        <div className="forecast-tile">
          <div className="label">Today so far</div>
          <div className="value">{today_kwh.toFixed(1)}<span className="unit">kWh</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Expected rest of day</div>
          <div className="value">{expected_remaining_kwh.toFixed(1)}<span className="unit">kWh</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Projected total</div>
          <div className="value">{(today_kwh + expected_remaining_kwh).toFixed(1)}<span className="unit">kWh</span></div>
        </div>
      </div>
      {zoom.isZoomed && (
        <button onClick={zoom.reset} style={{ marginTop: 6 }}>Reset zoom</button>
      )}
      <div className="chart-wrap" style={{ height: 320, marginTop: 12, userSelect: "none" }}>
        <ResponsiveContainer>
          <ComposedChart
            data={rows}
            margin={{ top: 10, right: 20, left: 0, bottom: 0 }}
            {...zoom.chartProps}
          >
            <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
            <XAxis
              dataKey="minute"
              type="number"
              domain={zoom.domain}
              allowDataOverflow
              stroke="#8b97a8"
              tick={{ fill: "#8b97a8", fontSize: 11 }}
              tickFormatter={fmtMinute}
              minTickGap={40}
            />
            <YAxis
              stroke="#8b97a8"
              tick={{ fill: "#8b97a8", fontSize: 11 }}
              label={{ value: "Watts", angle: -90, position: "insideLeft", fill: "#8b97a8", fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
              labelStyle={{ color: "#8b97a8" }}
              labelFormatter={fmtMinute}
            />
            <Legend wrapperStyle={{ color: "#8b97a8", fontSize: 12 }} />
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
            <Area
              type="monotone"
              dataKey="Clearsky"
              fill="#d29922"
              stroke="#d29922"
              fillOpacity={0.08}
              strokeOpacity={0.4}
              strokeDasharray="3 3"
              isAnimationActive={false}
              name="Clear-sky max"
            />
            <Line
              type="monotone"
              dataKey="Historical"
              stroke="#8b97a8"
              strokeWidth={2}
              strokeDasharray="4 2"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="Actual"
              stroke="#2ea043"
              strokeWidth={3}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="Load"
              stroke="#f85149"
              strokeWidth={1.5}
              strokeOpacity={0.6}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
