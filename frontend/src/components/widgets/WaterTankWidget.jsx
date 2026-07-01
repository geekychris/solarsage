import React from "react";

function levelColor(percent) {
  if (percent == null) return "#888";
  if (percent <= 10) return "#ef6f6c";
  if (percent <= 25) return "#ff9b6c";
  if (percent <= 50) return "#ffd166";
  return "#6cd1ff";
}

function formatDays(d) {
  if (d == null) return null;
  if (d < 1) return "<1 day";
  if (d < 45) return `${Math.round(d)} days`;
  const months = d / 30;
  if (months < 6) return `${months.toFixed(1)} months`;
  return `${Math.round(months)} months`;
}

export default function WaterTankWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const p = data.percent;
  const color = levelColor(p);
  const days = formatDays(data.days_remaining);

  return (
    <div className="water-tank">
      <div className="water-tank-top">
        <div className="water-tank-big" style={{ color }}>
          {p != null ? `${p.toFixed(0)}%` : "—"}
        </div>
        <div className="water-tank-sub">
          <div>
            <strong>{data.depth_ft?.toFixed(2)} ft</strong>
            <span className="muted"> of {data.full_ft?.toFixed(1)} ft</span>
          </div>
          {data.gallons != null && (
            <div className="muted">
              ~{data.gallons.toLocaleString()} gal remaining
            </div>
          )}
          {days && (
            <div className="muted">
              ~{days} to empty at current usage
            </div>
          )}
          {data.rate_ft_per_day != null && (
            <div className="muted" style={{ fontSize: 11 }}>
              rate: {(data.rate_ft_per_day * 12).toFixed(2)} in/day
            </div>
          )}
        </div>
      </div>

      <div className="water-tank-bar-outer">
        <div
          className="water-tank-bar-inner"
          style={{
            width: `${Math.max(2, Math.min(100, p || 0))}%`,
            background: color,
          }}
        />
        {[10, 25, 50].map((t) => (
          <div
            key={t}
            className="water-tank-tick"
            style={{ left: `${t}%` }}
            title={`${t}% warning`}
          />
        ))}
      </div>

      {data.trend && (
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          7d high: {data.trend.max_7d_ft != null
            ? `${data.trend.max_7d_ft.toFixed(2)} ft`
            : "—"}
          {"  ·  "}24h high: {data.trend.max_24h_ft != null
            ? `${data.trend.max_24h_ft.toFixed(2)} ft`
            : "—"}
        </div>
      )}
    </div>
  );
}
