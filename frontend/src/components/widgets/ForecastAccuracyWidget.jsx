import React, { useMemo } from "react";

export default function ForecastAccuracyWidget({ data }) {
  const chart = useMemo(() => {
    const arr = (data?.per_day || []).filter(
      (d) => d.forecast_kwh != null && d.actual_kwh != null
    );
    if (!arr.length) return null;
    const w = 600, h = 140, padL = 30, padB = 22;
    const maxKwh = Math.max(1, ...arr.flatMap((d) => [d.forecast_kwh, d.actual_kwh]));
    const barW = (w - padL) / arr.length;
    return { w, h, padL, padB, maxKwh, barW, arr };
  }, [data]);

  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;
  const s = data.summary || {};

  return (
    <div className="fc-accuracy">
      {s.days > 0 && (
        <div className="fc-summary">
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Avg forecast</div>
            <div className="fc-big">{s.avg_forecast_kwh?.toFixed(1)} kWh</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Avg actual</div>
            <div className="fc-big">{s.avg_actual_kwh?.toFixed(1)} kWh</div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Bias ({s.days} d)</div>
            <div className={`fc-big ${s.avg_error_kwh > 0 ? "fc-plus" : "fc-minus"}`}>
              {s.avg_error_kwh > 0 ? "+" : ""}{s.avg_error_kwh?.toFixed(1)} kWh
              <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
                ({s.avg_error_pct > 0 ? "+" : ""}{s.avg_error_pct}%)
              </span>
            </div>
          </div>
        </div>
      )}
      {chart && (
        <svg width="100%" viewBox={`0 0 ${chart.w} ${chart.h}`} className="fc-svg">
          {[0.25, 0.5, 0.75, 1].map((f, i) => {
            const y = chart.padB + (chart.h - chart.padB) * (1 - f);
            return (
              <g key={i}>
                <line x1={chart.padL} x2={chart.w} y1={y} y2={y}
                      stroke="rgba(255,255,255,0.06)" />
                <text x={chart.padL - 4} y={y + 3} textAnchor="end"
                      fill="#888" fontSize="9">
                  {(chart.maxKwh * f).toFixed(0)}
                </text>
              </g>
            );
          })}
          {chart.arr.map((d, i) => {
            const x = chart.padL + i * chart.barW;
            const fw = Math.max(1, chart.barW / 2 - 1);
            const fh = (d.forecast_kwh / chart.maxKwh) * (chart.h - chart.padB);
            const ah = (d.actual_kwh   / chart.maxKwh) * (chart.h - chart.padB);
            return (
              <g key={d.date}>
                <rect x={x + 1} y={chart.h - chart.padB - fh}
                      width={fw} height={fh} fill="#6cd1ff" fillOpacity={0.6}>
                  <title>{d.date}: forecast {d.forecast_kwh} kWh</title>
                </rect>
                <rect x={x + 1 + fw + 1} y={chart.h - chart.padB - ah}
                      width={fw} height={ah} fill="#ffd166" fillOpacity={0.7}>
                  <title>{d.date}: actual {d.actual_kwh} kWh (err {d.error_pct}%)</title>
                </rect>
              </g>
            );
          })}
          <text x={chart.padL} y={chart.h - 6} fill="#888" fontSize="10">
            <tspan fill="#6cd1ff">■</tspan> forecast   <tspan fill="#ffd166">■</tspan> actual
          </text>
        </svg>
      )}
      <div className="muted" style={{ fontSize: 11 }}>
        peak_kw {s.peak_kw_used} · {data.window_days} d window ·
        {" "}bias {s.avg_error_pct > 0 ? "over" : "under"}-producing on avg
      </div>
    </div>
  );
}
