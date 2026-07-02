import React, { useMemo, useState } from "react";
import { api } from "../../api.js";

const SENSOR_COLORS = [
  "#6cd1ff", "#ffd166", "#6fdc8c", "#ef6f6c",
  "#c54a8c", "#ff9b6c", "#a29bfe", "#00cec9",
];

function timeLabel(iso, window_hours) {
  const d = new Date(iso);
  if (window_hours <= 48) {
    return `${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`;
  }
  return d.toLocaleDateString(undefined, { weekday: "short", month: "numeric", day: "numeric" });
}

function seriesPath(values, xScale, yScale) {
  let out = "";
  let started = false;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null) { started = false; continue; }
    out += (started ? "L" : "M") + xScale(i).toFixed(1) + "," + yScale(v).toFixed(1);
    started = true;
  }
  return out;
}

export default function ClimateChartWidget({ data, onChanged }) {
  const [showKind, setShowKind] = useState("temp"); // "temp" | "humidity" | "both"
  const [hover, setHover] = useState(null);
  const [changing, setChanging] = useState(false);

  const chart = useMemo(() => {
    if (!data?.times?.length) return null;
    const width = 640, height = 260;
    const padL = 36, padR = 8, padT = 8, padB = 22;
    const w = width - padL - padR;
    const h = height - padT - padB;
    const n = data.times.length;

    // Y range from whichever series are being shown
    const values = [];
    for (const s of data.sensors || []) {
      if (showKind !== "humidity" && s.temp_series) {
        for (const v of s.temp_series) if (v != null && Number.isFinite(v)) values.push(v);
      }
      if (showKind !== "temp" && s.humidity_series) {
        for (const v of s.humidity_series) if (v != null && Number.isFinite(v)) values.push(v);
      }
    }
    if (!values.length) return null;
    let minY = Math.min(...values);
    let maxY = Math.max(...values);
    const pad = Math.max(1, (maxY - minY) * 0.08);
    minY -= pad; maxY += pad;
    if (maxY - minY < 2) maxY = minY + 2;

    const xScale = (i) => padL + (i / Math.max(1, n - 1)) * w;
    const yScale = (v) => padT + h - ((v - minY) / (maxY - minY)) * h;

    return { width, height, padL, padR, padT, padB, w, h, n, xScale, yScale, minY, maxY };
  }, [data, showKind]);

  async function switchWindow(hours) {
    setChanging(true);
    try {
      const cur = await api.getWidgetConfig("climate_chart");
      await api.putWidgetConfig("climate_chart", {
        ...cur.config, window_hours: hours,
      });
      if (onChanged) await onChanged();
    } finally {
      setChanging(false);
    }
  }

  if (!data) return <div className="muted">Loading…</div>;
  const sensors = data.sensors || [];
  const window_hours = data.window_hours;

  if (!chart) {
    return (
      <div>
        <div className="muted" style={{ fontSize: 12 }}>
          No history yet — HA hasn't accumulated readings for the
          configured entities.
        </div>
      </div>
    );
  }

  const { width, height, xScale, yScale, padL, padT, padB, h, n } = chart;

  function onMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const scale = width / rect.width;
    const px = (e.clientX - rect.left) * scale;
    const idx = Math.round(((px - padL) / chart.w) * (n - 1));
    if (idx >= 0 && idx < n) setHover(idx);
  }

  return (
    <div className="climate-chart">
      <div className="climate-toolbar">
        <div className="climate-window">
          {[
            { label: "24 h", hours: 24 },
            { label: "3 d",  hours: 72 },
            { label: "7 d",  hours: 168 },
          ].map((w) => (
            <button
              key={w.hours}
              type="button"
              className={window_hours === w.hours ? "active" : ""}
              disabled={changing}
              onClick={() => switchWindow(w.hours)}
            >{w.label}</button>
          ))}
        </div>
        <div className="climate-kind">
          {[
            { label: "Temp",  kind: "temp" },
            { label: "Humid", kind: "humidity" },
            { label: "Both",  kind: "both" },
          ].map((k) => (
            <button
              key={k.kind}
              type="button"
              className={showKind === k.kind ? "active" : ""}
              onClick={() => setShowKind(k.kind)}
            >{k.label}</button>
          ))}
        </div>
        <div className="muted climate-toolbar-note">
          {data.bucket_minutes}-min buckets · {sensors.length} sensor{sensors.length !== 1 ? "s" : ""}
        </div>
      </div>

      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        className="climate-svg"
      >
        {/* Y grid + labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
          const y = padT + h - h * f;
          const v = (chart.minY + (chart.maxY - chart.minY) * f).toFixed(0);
          return (
            <g key={i}>
              <line x1={padL} x2={width - 8} y1={y} y2={y}
                    stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
              <text x={padL - 4} y={y + 3} textAnchor="end"
                    fill="#888" fontSize="10">{v}</text>
            </g>
          );
        })}
        {/* X labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
          const idx = Math.floor(f * (n - 1));
          return (
            <text key={i} x={xScale(idx)} y={height - 6} textAnchor="middle"
                  fill="#888" fontSize="10">
              {timeLabel(data.times[idx], window_hours)}
            </text>
          );
        })}
        {/* Lines */}
        {sensors.map((s, si) => {
          const color = SENSOR_COLORS[si % SENSOR_COLORS.length];
          return (
            <g key={si}>
              {showKind !== "humidity" && s.temp_series && (
                <path d={seriesPath(s.temp_series, xScale, yScale)}
                      stroke={color} strokeWidth="1.5" fill="none" />
              )}
              {showKind !== "temp" && s.humidity_series && (
                <path d={seriesPath(s.humidity_series, xScale, yScale)}
                      stroke={color} strokeWidth="1.5" fill="none"
                      strokeDasharray="4 3" />
              )}
            </g>
          );
        })}
        {/* Hover crosshair */}
        {hover != null && (
          <line x1={xScale(hover)} x2={xScale(hover)} y1={padT} y2={padT + h}
                stroke="#fff" strokeOpacity="0.4" />
        )}
      </svg>

      <div className="climate-legend">
        {sensors.map((s, si) => {
          const color = SENSOR_COLORS[si % SENSOR_COLORS.length];
          const t = hover != null ? s.temp_series?.[hover] : null;
          const humidity = hover != null ? s.humidity_series?.[hover] : null;
          const t_now = s.temp_series?.[s.temp_series.length - 1];
          const h_now = s.humidity_series?.[s.humidity_series.length - 1];
          return (
            <div key={si} className="climate-leg-row">
              <span className="climate-swatch" style={{ background: color }} />
              <strong style={{ minWidth: 80 }}>{s.name}</strong>
              {showKind !== "humidity" && (
                <span className="climate-val">
                  {hover != null
                    ? (t != null ? `${t.toFixed(1)}${s.temp_unit || ""}` : "—")
                    : (t_now != null ? `${t_now.toFixed(1)}${s.temp_unit || ""}` : "—")}
                </span>
              )}
              {showKind !== "temp" && (
                <span className="climate-val climate-val-hum">
                  💧 {hover != null
                    ? (humidity != null ? `${humidity.toFixed(0)}${s.humidity_unit || "%"}` : "—")
                    : (h_now != null ? `${h_now.toFixed(0)}${s.humidity_unit || "%"}` : "—")}
                </span>
              )}
            </div>
          );
        })}
        {hover != null && (
          <div className="muted climate-hover-time">
            @ {timeLabel(data.times[hover], window_hours)}
          </div>
        )}
      </div>
    </div>
  );
}
