import React, { useMemo, useState } from "react";

const SERIES = [
  { key: "pv_kw",   label: "PV",   color: "#ffd166", fill: "rgba(255,209,102,0.20)" },
  { key: "load_kw", label: "Load", color: "#6cd1ff", fill: "none" },
  { key: "ac_kw",   label: "AC",   color: "#ef6f6c", fill: "rgba(239,111,108,0.15)" },
];

function timeHHmm(iso) {
  const d = new Date(iso);
  return `${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`;
}

function seriesPath(values, times, xScale, yScale, height) {
  const pts = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null) continue;
    pts.push([xScale(i), yScale(v)]);
  }
  if (!pts.length) return "";
  return pts.reduce((acc, [x, y], i) => acc + `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`, "");
}

function areaPath(values, times, xScale, yScale, height, baseY) {
  const pts = [];
  let started = false;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v == null) { started = false; continue; }
    const x = xScale(i);
    const y = yScale(v);
    if (!started) {
      pts.push(`M${x.toFixed(1)},${baseY} L${x.toFixed(1)},${y.toFixed(1)}`);
      started = true;
    } else {
      pts.push(`L${x.toFixed(1)},${y.toFixed(1)}`);
    }
  }
  if (!started) return "";
  const lastIdx = values.length - 1;
  pts.push(`L${xScale(lastIdx).toFixed(1)},${baseY} Z`);
  return pts.join(" ");
}

export default function AcPvOverlayWidget({ data }) {
  const [hover, setHover] = useState(null);
  const chart = useMemo(() => {
    if (!data || !data.times?.length) return null;
    const width = 640;
    const height = 220;
    const padL = 32, padR = 8, padT = 8, padB = 22;
    const w = width - padL - padR;
    const h = height - padT - padB;
    const n = data.times.length;

    const allValues = [];
    for (const s of SERIES) {
      const arr = data[s.key] || [];
      for (const v of arr) if (v != null && Number.isFinite(v)) allValues.push(v);
    }
    const maxY = Math.max(0.5, Math.ceil(Math.max(...allValues, 1) * 1.1 * 2) / 2);

    const xScale = (i) => padL + (i / Math.max(1, n - 1)) * w;
    const yScale = (v) => padT + h - (v / maxY) * h;
    const baseY = padT + h;

    return {
      width, height, padL, padR, padT, padB, w, h, n,
      xScale, yScale, baseY, maxY,
    };
  }, [data]);

  if (!data) return <div className="muted">Loading…</div>;
  if (!chart) return <div className="muted">No history samples yet.</div>;

  const { width, height, xScale, yScale, baseY, maxY, padL, padT, h, n } = chart;

  // Sunset marker (from data) — could pull from another widget, skip for now.
  const now = new Date();
  const nowMs = now.getTime();
  const startMs = new Date(data.times[0]).getTime();
  const endMs   = new Date(data.times[n - 1]).getTime();
  const nowX = padL + ((nowMs - startMs) / Math.max(1, endMs - startMs)) * chart.w;

  // Hover index → nearest bucket
  function onMove(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const idx = Math.round(((px - padL) / chart.w) * (n - 1));
    if (idx >= 0 && idx < n) setHover(idx);
  }

  return (
    <div className="acpv-overlay">
      <div className="acpv-legend">
        {SERIES.map((s) => (
          <span key={s.key} className="acpv-leg">
            <span className="acpv-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
        <span className="muted acpv-legend-note">
          Last 24 h · {data.bucket_minutes}-min buckets
        </span>
      </div>
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        className="acpv-svg"
      >
        {/* Y grid */}
        {[0.25, 0.5, 0.75, 1].map((f, i) => {
          const y = padT + h - h * f;
          const kw = (maxY * f).toFixed(1);
          return (
            <g key={i}>
              <line x1={padL} x2={width - 8} y1={y} y2={y}
                    stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
              <text x={padL - 4} y={y + 3} textAnchor="end"
                    fill="#888" fontSize="10">{kw}</text>
            </g>
          );
        })}
        {/* X labels — 6-hour ticks */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
          const idx = Math.floor(f * (n - 1));
          const x = xScale(idx);
          return (
            <text key={i} x={x} y={height - 6} textAnchor="middle"
                  fill="#888" fontSize="10">
              {timeHHmm(data.times[idx])}
            </text>
          );
        })}
        {/* PV area (behind everything) */}
        <path d={areaPath(data.pv_kw, data.times, xScale, yScale, h, baseY)}
              fill={SERIES[0].fill} stroke="none" />
        {/* AC area */}
        <path d={areaPath(data.ac_kw, data.times, xScale, yScale, h, baseY)}
              fill={SERIES[2].fill} stroke="none" />
        {/* Lines */}
        {SERIES.map((s) => (
          <path key={s.key}
                d={seriesPath(data[s.key] || [], data.times, xScale, yScale, h)}
                stroke={s.color} strokeWidth="1.5" fill="none" />
        ))}
        {/* Now line */}
        {nowMs >= startMs && nowMs <= endMs && (
          <line x1={nowX} x2={nowX} y1={padT} y2={baseY}
                stroke="#fff" strokeOpacity="0.35" strokeDasharray="2,3" />
        )}
        {/* Hover crosshair */}
        {hover != null && (
          <line x1={xScale(hover)} x2={xScale(hover)} y1={padT} y2={baseY}
                stroke="#fff" strokeOpacity="0.5" />
        )}
      </svg>
      {hover != null && (
        <div className="acpv-tip muted" style={{ fontSize: 12 }}>
          <strong>{timeHHmm(data.times[hover])}</strong>
          {SERIES.map((s) => (
            <span key={s.key} style={{ marginLeft: 10 }}>
              <span className="acpv-swatch" style={{ background: s.color }} />
              {s.label}: <strong>{data[s.key]?.[hover]?.toFixed(2) ?? "—"}</strong> kW
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
