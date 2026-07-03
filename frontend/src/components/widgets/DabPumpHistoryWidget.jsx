import React, { useState } from "react";

function BarChart({ data, keyLabel, colour, unit = "gal" }) {
  if (!data || data.length === 0) {
    return <div className="muted" style={{ fontSize: 12 }}>No data.</div>;
  }
  const w = 300;
  const h = 90;
  const pad = 24;
  const inner = h - pad;
  const barW = (w - 8) / data.length;
  const realVals = data.map((d) => d.gallons).filter((v) => v != null);
  const maxVal = Math.max(1, ...realVals, 0);
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
          const val = d.gallons;
          const x = i * barW + 2;
          const isFuture = d.future === true || val == null;
          if (isFuture) {
            // Faint placeholder rect so the chart doesn't lose its shape.
            return (
              <rect
                key={i}
                x={x} y={inner - 3}
                width={Math.max(1, barW - 2)}
                height={3}
                fill="currentColor" fillOpacity="0.08"
              />
            );
          }
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
  const [dayOffset, setDayOffset] = useState(0);
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const daysHourly = data.days_hourly || [];
  const maxOffset = Math.max(0, daysHourly.length - 1);
  const clampedOffset = Math.min(dayOffset, maxOffset);
  const selectedDay = daysHourly[clampedOffset] || null;

  const hourlySeries = selectedDay?.by_hour || [];
  const daySeries = data.by_day || [];
  const series = view === "hour" ? hourlySeries : daySeries;
  const keyLabel = view === "hour" ? "hour" : "label";
  const colour = view === "hour" ? "#6cd1ff" : "#6fdc8c";

  const hourlyPeak = selectedDay?.peak || null;
  const hourlyTotal = selectedDay?.total ?? 0;

  return (
    <div className="dab-hist">
      <div className="dab-hist-head">
        <div className="dab-hist-toggle">
          <button
            className={view === "hour" ? "active" : ""}
            onClick={() => setView("hour")}
          >1d</button>
          <button
            className={view === "day" ? "active" : ""}
            onClick={() => setView("day")}
          >7d</button>
        </div>
        {view === "hour" && daysHourly.length > 0 && (
          <div className="dab-hist-daynav">
            <button
              type="button"
              disabled={clampedOffset >= maxOffset}
              onClick={() => setDayOffset(clampedOffset + 1)}
              title="Previous day"
            >‹</button>
            <div className="dab-hist-day">
              <div className="dab-hist-day-label">{selectedDay?.label}</div>
              <div className="muted" style={{ fontSize: 10 }}>{selectedDay?.date}</div>
            </div>
            <button
              type="button"
              disabled={clampedOffset <= 0}
              onClick={() => setDayOffset(clampedOffset - 1)}
              title="Next day"
            >›</button>
          </div>
        )}
        <div className="dab-hist-summary">
          {view === "hour" ? (
            <>
              <div>
                <span className="muted" style={{ fontSize: 11 }}>Total</span>
                <div className="dab-hist-big">{hourlyTotal.toFixed(1)} gal</div>
              </div>
              {hourlyPeak && hourlyPeak.gallons > 0 && (
                <div>
                  <span className="muted" style={{ fontSize: 11 }}>Peak hour</span>
                  <div className="dab-hist-big">
                    {hourlyPeak.gallons.toFixed(1)}
                    <span className="dab-hist-sub"> · {hourlyPeak.hour}</span>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div>
                <span className="muted" style={{ fontSize: 11 }}>7d total</span>
                <div className="dab-hist-big">{data.total_7d?.toFixed(1)} gal</div>
              </div>
              <div>
                <span className="muted" style={{ fontSize: 11 }}>avg / day</span>
                <div className="dab-hist-big">{data.avg_daily?.toFixed(1)} gal</div>
              </div>
              {data.peak_day && data.peak_day.gallons > 0 && (
                <div>
                  <span className="muted" style={{ fontSize: 11 }}>peak day</span>
                  <div className="dab-hist-big">
                    {data.peak_day.gallons.toFixed(1)}
                    <span className="dab-hist-sub"> · {data.peak_day.label}</span>
                  </div>
                </div>
              )}
            </>
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
          Home Assistant has only {data.collected_hours < 24
            ? `${Math.round(data.collected_hours)}h`
            : `${Math.round(data.collected_hours / 24)}d`}
          {" "}of history for this sensor so far — earlier days will look empty
          until more data accumulates.
        </div>
      )}
    </div>
  );
}
