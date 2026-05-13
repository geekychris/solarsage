import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Brush,
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

// Channels we plot by default, plus their styling and which y-axis they use.
const CHANNELS = [
  { key: "ppv", label: "Solar PV", color: "#2ea043", width: 2, axis: "left" },
  { key: "consumptionPower", label: "Load (main)", color: "#f85149", width: 2, axis: "left" },
  { key: "peps", label: "Load (EPS)", color: "#ff9d76", width: 2, axis: "left" },
  { key: "pCharge", label: "Bat Charging", color: "#58a6ff", width: 2, axis: "left" },
  { key: "pDisCharge", label: "Bat Discharging", color: "#a371f7", width: 2, axis: "left" },
  { key: "pToGrid", label: "To Grid", color: "#d29922", width: 2, axis: "left" },
  { key: "pToUser", label: "From Grid", color: "#9b6dff", width: 2, axis: "left" },
  { key: "soc", label: "SoC %", color: "#79c0ff", width: 2, axis: "right" },
];

const PRESETS = [
  { label: "1d", days: 1 },
  { label: "3d", days: 3 },
  { label: "7d", days: 7 },
  { label: "14d", days: 14 },
  { label: "31d", days: 31 },
  { label: "90d", days: 90 },
];

const DEFAULT_HIDDEN = new Set(["pToGrid", "pToUser"]); // usually zero on this system

function fmtTick(ts, bucketLabel, tzOffsetMinutes) {
  const d = new Date(ts + (tzOffsetMinutes ?? 0) * 60_000 - (-new Date(ts).getTimezoneOffset()) * 60_000);
  // Compose a label suited to the bucket size
  switch (bucketLabel) {
    case "1d":
    case "6h":
      return d.toUTCString().split(" ").slice(1, 3).join(" "); // "08 May"
    case "1h":
      return d.toUTCString().slice(5, 16); // "08 May 14:00"
    case "15m":
    case "5m":
    case "1m":
    default:
      return d.toUTCString().slice(17, 22); // "14:30"
  }
}

function fmtTooltipLabel(ts, tzOffsetMinutes) {
  const local = new Date(ts + (tzOffsetMinutes ?? 0) * 60_000 - (-new Date(ts).getTimezoneOffset()) * 60_000);
  return local.toUTCString().slice(0, 22);
}

export default function RangeChart({ serial, tzOffsetMinutes }) {
  const [end, setEnd] = useState(Date.now());
  const [start, setStart] = useState(Date.now() - 7 * 86_400_000);
  const [presetLabel, setPresetLabel] = useState("7d");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [hidden, setHidden] = useState(DEFAULT_HIDDEN);
  // Drag-to-zoom state
  const [crosshair, setCrosshair] = useState(null);
  const [dragStart, setDragStart] = useState(null);
  const [dragEnd, setDragEnd] = useState(null);
  // For "Reset zoom"
  const lastPresetRef = useRef({ start: Date.now() - 7 * 86_400_000, end: Date.now(), label: "7d" });

  async function load(s, e) {
    setBusy(true);
    setErr("");
    try {
      const r = await api.range(serial, {
        start: s,
        end: e,
        fields: CHANNELS.map((c) => c.key).join(","),
        targetPoints: 500,
      });
      setData(r);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!serial) return;
    load(start, end);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial, start, end]);

  function pickPreset(p) {
    const e = Date.now();
    const s = e - p.days * 86_400_000;
    lastPresetRef.current = { start: s, end: e, label: p.label };
    setPresetLabel(p.label);
    setEnd(e);
    setStart(s);
  }

  function setEndDate(dateStr) {
    if (!dateStr) return;
    // Anchor end at end-of-day local for the picked date
    const [y, m, d] = dateStr.split("-").map(Number);
    const localEnd = new Date(y, m - 1, d, 23, 59, 59, 999).getTime();
    const span = end - start;
    setEnd(localEnd);
    setStart(localEnd - span);
    setPresetLabel("custom");
  }

  function resetZoom() {
    setStart(lastPresetRef.current.start);
    setEnd(lastPresetRef.current.end);
    setPresetLabel(lastPresetRef.current.label);
  }

  function toggleChannel(k) {
    setHidden((cur) => {
      const next = new Set(cur);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  // Merge series by ts for the chart row format
  const rows = useMemo(() => {
    if (!data) return [];
    const byTs = new Map();
    for (const [field, points] of Object.entries(data.series || {})) {
      for (const p of points) {
        const r = byTs.get(p.ts) || { ts: p.ts };
        r[field] = p.value;
        byTs.set(p.ts, r);
      }
    }
    return [...byTs.values()].sort((a, b) => a.ts - b.ts);
  }, [data]);

  function onMouseDown(e) {
    if (e?.activeLabel != null) {
      setDragStart(e.activeLabel);
      setDragEnd(e.activeLabel);
    }
  }
  function onMouseMove(e) {
    if (dragStart != null && e?.activeLabel != null) {
      setDragEnd(e.activeLabel);
    }
    if (e?.activePayload?.length) {
      setCrosshair(
        e.activePayload
          .filter((p) => p.value != null && Number.isFinite(p.value))
          .map((p) => ({ dataKey: p.dataKey, value: p.value, color: p.color || p.stroke }))
      );
    } else {
      setCrosshair(null);
    }
  }

  function onMouseLeave() {
    setDragStart(null);
    setDragEnd(null);
    setCrosshair(null);
  }
  function onMouseUp() {
    if (dragStart != null && dragEnd != null && dragStart !== dragEnd) {
      const a = Math.min(dragStart, dragEnd);
      const b = Math.max(dragStart, dragEnd);
      // Require at least 1 minute span — guards against accidental clicks
      if (b - a >= 60_000) {
        setStart(a);
        setEnd(b);
        setPresetLabel("custom");
      }
    }
    setDragStart(null);
    setDragEnd(null);
  }

  const bucketLabel = data?.bucket_label || "—";
  const spanDays = ((end - start) / 86_400_000).toFixed(2);
  const isZoomed = presetLabel === "custom" && lastPresetRef.current.label !== "custom";

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Range view</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          {data && `${spanDays} days · bucket ${bucketLabel} · ${rows.length} points`}
        </div>
      </div>

      <div className="toolbar" style={{ marginTop: 10 }}>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => pickPreset(p)}
            className={presetLabel === p.label ? "primary" : ""}
            disabled={busy}
          >
            {p.label}
          </button>
        ))}
        <span style={{ width: 8 }} />
        <label>End</label>
        <input
          type="date"
          value={new Date(end).toISOString().slice(0, 10)}
          onChange={(e) => setEndDate(e.target.value)}
        />
        {isZoomed && (
          <button onClick={resetZoom}>Reset zoom</button>
        )}
        {busy && <span className="muted">loading…</span>}
      </div>

      <div className="toolbar" style={{ marginTop: 4, fontSize: 12 }}>
        <span className="muted">Channels:</span>
        {CHANNELS.map((c) => (
          <label key={c.key} style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={!hidden.has(c.key)}
              onChange={() => toggleChannel(c.key)}
            />
            <span style={{ color: c.color }}>{c.label}</span>
          </label>
        ))}
      </div>

      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}

      {rows.length === 0 && !busy ? (
        <div className="empty">No data in this range. Pick a wider window or click <strong>Sync</strong> in the top bar.</div>
      ) : (
        <div className="chart-wrap" style={{ height: 420, marginTop: 12, userSelect: "none" }}>
          <ResponsiveContainer>
            <LineChart
              data={rows}
              margin={{ top: 10, right: 50, left: 0, bottom: 0 }}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={onMouseLeave}
            >
              <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
              <XAxis
                dataKey="ts"
                type="number"
                domain={["dataMin", "dataMax"]}
                scale="time"
                stroke="#8b97a8"
                tick={{ fill: "#8b97a8", fontSize: 11 }}
                tickFormatter={(ts) => fmtTick(ts, bucketLabel, tzOffsetMinutes)}
                minTickGap={50}
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
                domain={[0, 100]}
                tick={{ fill: "#8b97a8", fontSize: 11 }}
                label={{ value: "SoC %", angle: 90, position: "insideRight", fill: "#8b97a8", fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
                labelStyle={{ color: "#8b97a8" }}
                labelFormatter={(ts) => fmtTooltipLabel(ts, tzOffsetMinutes)}
                formatter={(v, k) => [`${Math.round(v).toLocaleString()}`, k]}
              />
              <Legend
                wrapperStyle={{ color: "#8b97a8", fontSize: 12 }}
                formatter={(v) => CHANNELS.find((c) => c.key === v)?.label || v}
              />
              <ReferenceLine y={0} yAxisId="left" stroke="#444" />
              {CHANNELS.filter((c) => !hidden.has(c.key)).map((c) => (
                <Line
                  key={c.key}
                  yAxisId={c.axis}
                  type="monotone"
                  dataKey={c.key}
                  stroke={c.color}
                  strokeWidth={c.width}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
              {(crosshair || []).map((p) => {
                const channel = CHANNELS.find((c) => c.key === p.dataKey);
                return (
                  <ReferenceLine
                    key={`xh-${p.dataKey}`}
                    y={p.value}
                    yAxisId={channel?.axis || "left"}
                    stroke={p.color}
                    strokeDasharray="2 3"
                    strokeOpacity={0.55}
                    ifOverflow="extendDomain"
                  />
                );
              })}
              {dragStart != null && dragEnd != null && (
                <ReferenceArea
                  yAxisId="left"
                  x1={Math.min(dragStart, dragEnd)}
                  x2={Math.max(dragStart, dragEnd)}
                  strokeOpacity={0.3}
                  fill="#58a6ff"
                  fillOpacity={0.15}
                />
              )}
              <Brush
                dataKey="ts"
                height={28}
                stroke="#58a6ff"
                travellerWidth={8}
                tickFormatter={(ts) => fmtTick(ts, bucketLabel, tzOffsetMinutes)}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        <strong>Tips:</strong> click + drag on the chart to zoom into a region · use the bottom Brush to scrub · "Reset zoom" returns to the last preset.
      </div>
    </div>
  );
}
