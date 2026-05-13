import React, { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
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

const RANGES = [
  { label: "15m", minutes: 15 },
  { label: "1h", minutes: 60 },
  { label: "6h", minutes: 360 },
  { label: "24h", minutes: 1440 },
  { label: "7d", minutes: 10080 },
  { label: "30d", minutes: 43200 },
];

function formatTs(ts, range) {
  const d = new Date(ts);
  if (range <= 60) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  if (range <= 1440) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" });
}

export default function HistoryChart({ serial }) {
  const [metrics, setMetrics] = useState([]);
  const [field, setField] = useState("");
  const [rangeMin, setRangeMin] = useState(60);
  const [points, setPoints] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const zoom = useChartZoom({ minSpan: 1000 });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setErr("");
      try {
        const r = await api.metrics(serial);
        if (cancelled) return;
        setMetrics(r.metrics || []);
        if ((r.metrics || []).length && !field) {
          // sensible default
          const prefer = ["ppv", "ppvpCharge", "consumptionPower", "pToGrid"];
          const pick = prefer.find((p) => r.metrics.some((m) => m.field === p));
          setField(pick || r.metrics[0].field);
        }
      } catch (ex) {
        setErr(ex.message);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // re-load metrics when inverter changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial]);

  useEffect(() => {
    if (!field || !serial) return;
    let cancelled = false;
    async function load() {
      setBusy(true);
      setErr("");
      try {
        const r = await api.history(serial, field, rangeMin);
        if (cancelled) return;
        setPoints(r.points || []);
      } catch (ex) {
        if (!cancelled) setErr(ex.message);
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    load();
    const id = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [serial, field, rangeMin]);

  const grouped = useMemo(() => {
    // group metrics by category for the dropdown
    const g = new Map();
    for (const m of metrics) {
      if (!g.has(m.category)) g.set(m.category, []);
      g.get(m.category).push(m.field);
    }
    return g;
  }, [metrics]);

  const data = useMemo(
    () => points.map((p) => ({ ts: p.ts, value: p.value, label: formatTs(p.ts, rangeMin) })),
    [points, rangeMin]
  );

  return (
    <div className="panel">
      <h3>History</h3>
      <div className="toolbar">
        <label>Metric</label>
        <select value={field} onChange={(e) => setField(e.target.value)}>
          {[...grouped.entries()].map(([cat, fields]) => (
            <optgroup label={cat} key={cat}>
              {fields.map((f) => (
                <option key={`${cat}.${f}`} value={f}>
                  {f}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <label>Range</label>
        {RANGES.map((r) => (
          <button
            key={r.minutes}
            className={r.minutes === rangeMin ? "primary" : ""}
            onClick={() => setRangeMin(r.minutes)}
          >
            {r.label}
          </button>
        ))}
        {busy && <span className="muted">loading…</span>}
      </div>
      {err && <div className="error">{err}</div>}
      {metrics.length === 0 ? (
        <div className="empty">
          No history yet — the server polls every 60s. Come back in a minute.
        </div>
      ) : data.length === 0 ? (
        <div className="empty">No samples for the selected range.</div>
      ) : (
        <>
          {zoom.isZoomed && (
            <button onClick={zoom.reset} style={{ marginTop: 6 }}>Reset zoom</button>
          )}
          <div className="chart-wrap" style={{ height: 320, userSelect: "none" }}>
            <ResponsiveContainer>
              <LineChart
                data={data}
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
                  tick={{ fill: "#8b97a8", fontSize: 11 }}
                  stroke="#8b97a8"
                  tickFormatter={(t) => formatTs(t, rangeMin)}
                  minTickGap={40}
                />
                <YAxis tick={{ fill: "#8b97a8", fontSize: 11 }} stroke="#8b97a8" />
                <Tooltip
                  contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
                  labelStyle={{ color: "#8b97a8" }}
                  labelFormatter={(t) => formatTs(t, rangeMin)}
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
                  dataKey="value"
                  stroke="#58a6ff"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  name={field}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
