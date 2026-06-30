import React from "react";

function Sparkline({ series }) {
  if (!series || series.length < 2) return null;
  const values = series.map((p) => p.rate);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 120;
  const h = 28;
  const stepX = w / (series.length - 1);
  const pts = series.map((p, i) => {
    const x = i * stepX;
    const y = h - ((p.rate - min) / span) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width={w} height={h} className="currency-spark">
      <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export default function CurrencyWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const latest = data.latest || {};
  const series = data.series || {};
  return (
    <div className="currency">
      <div className="muted" style={{ fontSize: 11 }}>
        as of {data.latest_date}
      </div>
      {Object.entries(latest).map(([q, rate]) => (
        <div key={q} className="currency-row">
          <span className="currency-pair">
            1 {data.base} = <strong>{Number(rate).toFixed(2)}</strong> {q}
          </span>
          <Sparkline series={series[q] || []} />
        </div>
      ))}
    </div>
  );
}
