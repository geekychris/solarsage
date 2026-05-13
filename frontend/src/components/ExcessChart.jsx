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

function fmtW(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString()}`;
}

export default function ExcessChart({ serial }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const zoom = useChartZoom({ minSpan: 15 });

  async function load() {
    try {
      const r = await api.excess(serial);
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
    Clearsky: Math.round(b.clearsky_w),
    ExpectedMax: Math.round(b.expected_max_w),
    ExpectedLoad: Math.round(b.expected_load_w || 0),
    Excess: Math.round(b.excess_w || 0),
    Actual: b.actual_pv_w == null ? null : Math.round(b.actual_pv_w),
    ActualLoad: b.actual_load_w == null ? null : Math.round(b.actual_load_w),
  }));

  const now = data.summary.now;
  const peak = data.summary.peak_excess_bucket;
  const totalExcessKwh = data.summary.total_excess_today_kwh;

  // Excess "as of now" rolled up from now → end of day, in kWh
  const remainingExcessKwh =
    data.buckets
      .filter((b) => b.minute_of_day > data.now_bucket)
      .reduce((s, b) => s + b.excess_w * (data.bucket_minutes / 60) / 1000, 0);

  // The current bucket's actual_pv vs expected_max → "are we hitting our potential?"
  const cur = data.buckets[Math.floor(data.now_bucket / data.bucket_minutes)] || null;
  let utilizationPct = null;
  if (cur && cur.actual_pv_w != null && cur.expected_max_w > 50) {
    utilizationPct = (cur.actual_pv_w / cur.expected_max_w) * 100;
  }

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Production headroom & excess</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          {data.days_of_history} days of history
        </div>
      </div>

      <div className="forecast-tiles">
        <div className="forecast-tile">
          <div className="label">Max producible now</div>
          <div className="value">{fmtW(now?.expected_max_w)}<span className="unit">W</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Expected load now</div>
          <div className="value">{fmtW(now?.expected_load_w)}<span className="unit">W</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Excess available now</div>
          <div className="value" style={{ color: now?.excess_w > 0 ? "#2ea043" : "#8b97a8" }}>
            {fmtW(now?.excess_w)}<span className="unit">W</span>
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">Utilization right now</div>
          <div className="value">
            {utilizationPct != null ? `${utilizationPct.toFixed(0)}` : "—"}
            <span className="unit">%</span>
          </div>
        </div>
        <div className="forecast-tile">
          <div className="label">Peak excess later</div>
          <div className="value" style={{ fontSize: 18 }}>
            {peak ? `${fmtW(peak.excess_w)} W` : "—"}
          </div>
          {peak && (
            <div className="muted" style={{ fontSize: 11 }}>
              at {fmtMinute(peak.minute_of_day)} local
            </div>
          )}
        </div>
        <div className="forecast-tile">
          <div className="label">Total excess today</div>
          <div className="value">{totalExcessKwh.toFixed(1)}<span className="unit">kWh</span></div>
        </div>
        <div className="forecast-tile">
          <div className="label">Remaining excess</div>
          <div className="value">{remainingExcessKwh.toFixed(1)}<span className="unit">kWh</span></div>
          <div className="muted" style={{ fontSize: 11 }}>from now till sunset</div>
        </div>
      </div>

      {zoom.isZoomed && (
        <button onClick={zoom.reset} style={{ marginTop: 6 }}>Reset zoom</button>
      )}
      <div className="chart-wrap" style={{ height: 360, marginTop: 14, userSelect: "none" }}>
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
            <ReferenceLine x={data.now_bucket} stroke="#58a6ff" strokeDasharray="3 3" label={{ value: "now", fill: "#58a6ff", fontSize: 11, position: "top" }} />
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
            {/* Clearsky theoretical envelope — thin orange dashed */}
            <Line
              type="monotone"
              dataKey="Clearsky"
              stroke="#d29922"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              strokeOpacity={0.5}
              dot={false}
              isAnimationActive={false}
              name="Clear-sky max"
            />
            {/* Expected max from history — bold green dashed ceiling */}
            <Line
              type="monotone"
              dataKey="ExpectedMax"
              stroke="#2ea043"
              strokeWidth={2.5}
              strokeDasharray="6 3"
              dot={false}
              isAnimationActive={false}
              name="Expected max (history)"
            />
            {/* Excess filled area between expected_max and expected_load */}
            <Area
              type="monotone"
              dataKey="Excess"
              fill="#58a6ff"
              fillOpacity={0.18}
              stroke="#58a6ff"
              strokeOpacity={0.6}
              strokeWidth={1.5}
              isAnimationActive={false}
              name="Excess available"
            />
            {/* Expected load — red */}
            <Line
              type="monotone"
              dataKey="ExpectedLoad"
              stroke="#f85149"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="Expected load (incl. AC)"
            />
            {/* Today's actual PV — solid bold green */}
            <Line
              type="monotone"
              dataKey="Actual"
              stroke="#3fb950"
              strokeWidth={3}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
              name="Actual PV today"
            />
            {/* Today's actual load — solid orange */}
            <Line
              type="monotone"
              dataKey="ActualLoad"
              stroke="#ff9d76"
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
              name="Actual load today"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="muted" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.6 }}>
        <strong>Expected max</strong> is the best PV your system has actually produced at that time of day across the last {data.days_of_history} days, capped by the clear-sky theoretical ceiling.
        <strong> Expected load</strong> is your historical average at that time — it captures the AC pattern (afternoons run higher).
        <strong> Excess</strong> is the headroom — how many watts you could deploy a discretionary load into without pulling from grid or battery.
        Forecast gets sharper as more days of history accumulate.
      </div>
    </div>
  );
}
