import React, { useState } from "react";

function BarChart({ data, keyLabel, colour, unit = "gal", pad = 24 }) {
  if (!data || data.length === 0) {
    return <div className="muted" style={{ fontSize: 12 }}>No data.</div>;
  }
  const w = 300;
  const h = 90;
  const inner = h - pad;
  const barW = (w - 8) / data.length;
  const maxVal = Math.max(1, ...data.map((d) => d.gallons || 0));
  const yScale = (v) => inner - (v / maxVal) * (inner - 4);
  const gridVals = [maxVal, maxVal * 0.5];
  return (
    <div className="dab-hist-chart">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
      >
        {gridVals.map((g, i) => (
          <g key={i}>
            <line
              x1={0} x2={w}
              y1={yScale(g)} y2={yScale(g)}
              stroke="currentColor" strokeOpacity="0.08" strokeDasharray="2 3"
            />
            <text
              x={2} y={yScale(g) - 2} fontSize={9}
              fill="currentColor" fillOpacity="0.4"
            >
              {g >= 100 ? g.toFixed(0) : g.toFixed(1)} {unit}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const val = d.gallons || 0;
          const x = i * barW + 2;
          const y = yScale(val);
          const barH = inner - y;
          return (
            <g key={i}>
              <title>{`${d[keyLabel]}: ${val.toFixed(1)} ${unit}`}</title>
              <rect
                x={x} y={y}
                width={Math.max(1, barW - 2)}
                height={Math.max(0, barH)}
                fill={colour}
                rx={2}
              />
            </g>
          );
        })}
        {data.map((d, i) => {
          // Sparse labels: every 4th for hourly, all for daily.
          if (data.length > 10 && i % 4 !== 0) return null;
          const x = i * barW + 2 + Math.max(0, barW - 2) / 2;
          return (
            <text
              key={`l${i}`}
              x={x} y={h - 3}
              fontSize={9} textAnchor="middle"
              fill="currentColor" fillOpacity="0.5"
            >
              {d[keyLabel]}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

export default function DabPumpHistoryWidget({ data }) {
  const [view, setView] = useState("hour");
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const series = view === "hour" ? data.by_hour : data.by_day;
  const keyLabel = view === "hour" ? "hour" : "label";
  const colour = view === "hour" ? "#6cd1ff" : "#6fdc8c";
  const total = view === "hour" ? data.total_24h : data.total_7d;
  const peak = view === "hour" ? data.peak_hour : data.peak_day;

  return (
    <div className="dab-hist">
      <div className="dab-hist-head">
        <div className="dab-hist-toggle">
          <button
            className={view === "hour" ? "active" : ""}
            onClick={() => setView("hour")}
          >24h</button>
          <button
            className={view === "day" ? "active" : ""}
            onClick={() => setView("day")}
          >7d</button>
        </div>
        <div className="dab-hist-summary">
          <div>
            <span className="muted" style={{ fontSize: 11 }}>
              {view === "hour" ? "24h total" : "7d total"}
            </span>
            <div className="dab-hist-big">{total?.toFixed(1)} gal</div>
          </div>
          {view === "day" && (
            <div>
              <span className="muted" style={{ fontSize: 11 }}>avg / day</span>
              <div className="dab-hist-big">{data.avg_daily?.toFixed(1)} gal</div>
            </div>
          )}
          {peak && peak.gallons > 0 && (
            <div>
              <span className="muted" style={{ fontSize: 11 }}>
                peak {view === "hour" ? "hour" : "day"}
              </span>
              <div className="dab-hist-big">
                {peak.gallons.toFixed(1)}
                <span className="dab-hist-sub"> · {peak[keyLabel]}</span>
              </div>
            </div>
          )}
        </div>
      </div>
      <BarChart
        data={series}
        keyLabel={keyLabel}
        colour={colour}
      />
      {data.collected_hours != null && data.collected_hours < 168 && (
        <div className="muted" style={{ fontSize: 10 }}>
          Only {data.collected_hours < 24
            ? `${Math.round(data.collected_hours)}h`
            : `${Math.round(data.collected_hours / 24)}d`}
          {" "}of history in HA so far — chart fills in as more data arrives.
        </div>
      )}
    </div>
  );
}
