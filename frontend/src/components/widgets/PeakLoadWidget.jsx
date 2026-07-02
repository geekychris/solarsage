import React, { useMemo } from "react";

function fmtDate(d) {
  return new Date(d + "T00:00:00").toLocaleDateString(undefined, {
    month: "short", day: "numeric",
  });
}
function fmtDateTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function PeakLoadWidget({ data }) {
  const chart = useMemo(() => {
    const arr = data?.per_day || [];
    if (!arr.length) return null;
    const w = 600, h = 120, padL = 30, padB = 22;
    const maxKw = Math.max(1, ...arr.map((d) => d.peak_kw));
    const barW = (w - padL) / arr.length;
    return { w, h, padL, padB, maxKw, barW };
  }, [data]);

  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;
  const overall = data.overall_peak_kw;
  const today = data.today_peak_kw;

  return (
    <div className="peak-load">
      <div className="peak-load-row">
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Overall peak (30 d)</div>
          <div className="peak-load-big">
            {overall != null ? `${overall.toFixed(1)} kW` : "—"}
          </div>
          {data.overall_peak_at && (
            <div className="muted" style={{ fontSize: 11 }}>
              {fmtDateTime(data.overall_peak_at)}
            </div>
          )}
        </div>
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Today's peak</div>
          <div className="peak-load-big">
            {today != null ? `${today.toFixed(1)} kW` : "—"}
          </div>
          {data.today_peak_at && (
            <div className="muted" style={{ fontSize: 11 }}>
              {fmtDateTime(data.today_peak_at)}
            </div>
          )}
        </div>
      </div>
      {chart && (
        <svg
          width="100%"
          viewBox={`0 0 ${chart.w} ${chart.h}`}
          className="peak-load-svg"
        >
          {[0.25, 0.5, 0.75, 1].map((f, i) => {
            const y = chart.padB + (chart.h - chart.padB) * (1 - f);
            return (
              <g key={i}>
                <line x1={chart.padL} x2={chart.w} y1={y} y2={y}
                      stroke="rgba(255,255,255,0.06)" />
                <text x={chart.padL - 4} y={y + 3} textAnchor="end"
                      fill="#888" fontSize="9">
                  {(chart.maxKw * f).toFixed(1)}
                </text>
              </g>
            );
          })}
          {data.per_day.map((d, i) => {
            const barH = (d.peak_kw / chart.maxKw) * (chart.h - chart.padB);
            const x = chart.padL + i * chart.barW;
            const y = chart.h - chart.padB - barH;
            const color = d.peak_kw >= chart.maxKw * 0.9 ? "#ef6f6c" : "#ffd166";
            return (
              <rect
                key={d.date}
                x={x + 1} y={y}
                width={Math.max(1, chart.barW - 2)} height={barH}
                fill={color} fillOpacity={0.7}
              >
                <title>{fmtDate(d.date)}: {d.peak_kw.toFixed(2)} kW</title>
              </rect>
            );
          })}
        </svg>
      )}
      <div className="muted" style={{ fontSize: 11 }}>
        {data.per_day?.length} days · field <code>{data.field}</code>
      </div>
    </div>
  );
}
