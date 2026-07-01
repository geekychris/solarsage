import React, { useMemo, useState } from "react";

function fmtClock(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    weekday: "short", hour: "numeric", minute: "2-digit",
  });
}

function ExcessBar({ hourly }) {
  const chart = useMemo(() => {
    const width = 320, height = 40, pad = 2;
    const w = width - pad * 2;
    const n = hourly.length || 1;
    const maxKw = Math.max(0.5, ...hourly.map((h) => h.excess_kw || 0));
    return { width, height, pad, w, n, maxKw };
  }, [hourly]);

  return (
    <svg width="100%" viewBox={`0 0 ${chart.width} ${chart.height}`} className="wtr-excess-bar">
      {hourly.map((h, i) => {
        const kw = h.excess_kw || 0;
        const barW = chart.w / chart.n;
        const barH = (kw / chart.maxKw) * chart.height;
        return (
          <rect
            key={i}
            x={chart.pad + i * barW}
            y={chart.height - barH}
            width={Math.max(1, barW - 1)}
            height={barH}
            fill="#ffd166"
            fillOpacity={0.7}
          >
            <title>
              {fmtClock(h.time)} — {kw.toFixed(1)} kW excess
            </title>
          </rect>
        );
      })}
    </svg>
  );
}

export default function WhenToRunWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const recs = data.recommendations || [];
  const hourly = data.hourly || [];

  return (
    <div className="wtr">
      <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
        {hourly.length} h forecast · peak {data.site?.peak_kw} kW ·
        baseline {data.site?.baseline_kw} kW
      </div>
      <ExcessBar hourly={hourly} />
      <div className="wtr-list">
        {recs.length === 0 && (
          <div className="muted" style={{ fontSize: 12 }}>
            No appliances configured. Add some in Widget config →
            "When to run" → appliances.
          </div>
        )}
        {recs.map((r, i) => {
          const rec = r.recommend;
          const fits = rec?.fits;
          const cls = rec ? (fits ? "fits" : "partial") : "no";
          return (
            <div key={i} className={`wtr-item ${cls}`}>
              <div className="wtr-item-head">
                <span className="wtr-name">{r.name}</span>
                <span className="muted"> · {r.kw} kW × {r.hours} h</span>
              </div>
              {rec ? (
                <div className="wtr-time">
                  <strong>{fits ? "▶ Start at" : "△ Try at"}</strong>
                  {" "}{fmtClock(rec.start)}
                  <span className="muted">
                    {" "}– {fmtClock(rec.end)}
                  </span>
                </div>
              ) : (
                <div className="muted">No fit in forecast horizon.</div>
              )}
              <div className="wtr-reason muted">{r.reason}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
