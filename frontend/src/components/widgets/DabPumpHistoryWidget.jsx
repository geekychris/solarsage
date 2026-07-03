import React, { useState } from "react";

// Round v up to a "nice" round number so the Y-axis ticks are readable.
// e.g. 1.3 → 2, 4.1 → 5, 13 → 15… well, 20 (we only allow 1/2/5/10).
function niceCeiling(v) {
  if (!Number.isFinite(v) || v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const mant = v / pow;
  if (mant <= 1) return 1 * pow;
  if (mant <= 2) return 2 * pow;
  if (mant <= 5) return 5 * pow;
  return 10 * pow;
}

function fmtGal(v) {
  if (v == null) return "—";
  if (v >= 100) return v.toFixed(0);
  if (v >= 10)  return v.toFixed(1);
  return v.toFixed(2);
}

// -------------- 1-day chart: 24 hourly bars, hour x-axis ------------------

function DayChart({ buckets }) {
  const W = 420, H = 150;
  const padL = 34, padR = 6, padT = 8, padB = 24;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const n = buckets.length;
  const barW = plotW / n;

  const realVals = buckets.map((b) => b.gallons).filter((v) => v != null);
  const yMax = niceCeiling(Math.max(...realVals, 0));
  const yScale = (v) => padT + plotH - (v / yMax) * plotH;
  const xTicks = [0, 3, 6, 9, 12, 15, 18, 21].map((h) => ({
    x: padL + h * barW + barW / 2,
    label: h === 0 ? "12a" : h === 12 ? "12p" : h < 12 ? `${h}a` : `${h - 12}p`,
  }));
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
    v: f * yMax,
    y: yScale(f * yMax),
  }));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet">
      {/* Y gridlines + labels */}
      {yTicks.map((t, i) => (
        <g key={`y${i}`}>
          <line
            x1={padL} x2={W - padR}
            y1={t.y} y2={t.y}
            stroke="currentColor"
            strokeOpacity={i === 0 ? 0.35 : 0.10}
            strokeDasharray={i === 0 ? undefined : "2 3"}
          />
          <text
            x={padL - 4} y={t.y + 3}
            fontSize={10} textAnchor="end"
            fill="currentColor" fillOpacity="0.6"
          >
            {fmtGal(t.v)}
          </text>
        </g>
      ))}
      {/* Y-axis label */}
      <text
        x={4} y={padT + plotH / 2}
        fontSize={9} fill="currentColor" fillOpacity="0.5"
        transform={`rotate(-90 8 ${padT + plotH / 2})`}
      >gallons</text>

      {/* Bars */}
      {buckets.map((b, i) => {
        const x = padL + i * barW + 1;
        if (b.future === true || b.gallons == null) {
          return (
            <rect
              key={i}
              x={x} y={padT + plotH - 2}
              width={Math.max(1, barW - 2)} height={2}
              fill="currentColor" fillOpacity={0.10}
            />
          );
        }
        const y = yScale(b.gallons);
        const bh = padT + plotH - y;
        return (
          <g key={i}>
            <title>{`${b.hour}: ${b.gallons.toFixed(1)} gal`}</title>
            <rect
              x={x} y={y}
              width={Math.max(1, barW - 2)}
              height={Math.max(0, bh)}
              fill="#6cd1ff" rx={1.5}
            />
          </g>
        );
      })}

      {/* X-axis line + ticks */}
      <line
        x1={padL} x2={W - padR}
        y1={padT + plotH} y2={padT + plotH}
        stroke="currentColor" strokeOpacity="0.35"
      />
      {xTicks.map((t, i) => (
        <g key={`x${i}`}>
          <line
            x1={t.x} x2={t.x}
            y1={padT + plotH} y2={padT + plotH + 3}
            stroke="currentColor" strokeOpacity="0.4"
          />
          <text
            x={t.x} y={padT + plotH + 14}
            fontSize={10} textAnchor="middle"
            fill="currentColor" fillOpacity="0.65"
          >
            {t.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

// -------------- 7-day chart: 168 hourly bars + daily-total overlay --------

function WeekChart({ daysHourly, byDay }) {
  const W = 420, H = 170;
  const padL = 34, padR = 34, padT = 10, padB = 26;
  const plotW = W - padL - padR, plotH = H - padT - padB;

  // Flatten: oldest day first, chronological order.
  const days = daysHourly.slice().reverse();          // [6d ago, …, today]
  const hourly = days.flatMap((d) =>
    d.by_hour.map((b) => ({ ...b, dayLabel: d.label })),
  );
  const dayW = plotW / 7;
  const barW = plotW / hourly.length;

  const realHourVals = hourly.map((b) => b.gallons).filter((v) => v != null);
  const yMaxHour = niceCeiling(Math.max(...realHourVals, 0));
  const yScaleHour = (v) => padT + plotH - (v / yMaxHour) * plotH;

  const dailyTotals = days.map((d) => d.total || 0);
  const yMaxDay = niceCeiling(Math.max(...dailyTotals, 0));
  const yScaleDay = (v) => padT + plotH - (v / yMaxDay) * plotH;

  const yTicksHour = [0, 0.25, 0.5, 0.75, 1].map((f) => ({
    v: f * yMaxHour, y: yScaleHour(f * yMaxHour),
  }));
  const yTicksDay = [0, 0.5, 1].map((f) => ({
    v: f * yMaxDay, y: yScaleDay(f * yMaxDay),
  }));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet">
      {/* Y gridlines (hourly axis, left) */}
      {yTicksHour.map((t, i) => (
        <g key={`yh${i}`}>
          <line
            x1={padL} x2={W - padR}
            y1={t.y} y2={t.y}
            stroke="currentColor"
            strokeOpacity={i === 0 ? 0.35 : 0.08}
            strokeDasharray={i === 0 ? undefined : "2 3"}
          />
          <text
            x={padL - 4} y={t.y + 3}
            fontSize={10} textAnchor="end"
            fill="#6cd1ff" fillOpacity="0.85"
          >
            {fmtGal(t.v)}
          </text>
        </g>
      ))}

      {/* Right Y axis (daily total) */}
      {yTicksDay.map((t, i) => (
        <text
          key={`yd${i}`}
          x={W - padR + 4} y={t.y + 3}
          fontSize={10} textAnchor="start"
          fill="#6fdc8c" fillOpacity="0.85"
        >
          {fmtGal(t.v)}
        </text>
      ))}

      {/* Rotated axis captions */}
      <text
        x={6} y={padT + plotH / 2}
        fontSize={9} fill="#6cd1ff" fillOpacity="0.7"
        transform={`rotate(-90 8 ${padT + plotH / 2})`}
      >gal / hour</text>
      <text
        x={W - 6} y={padT + plotH / 2}
        fontSize={9} fill="#6fdc8c" fillOpacity="0.7"
        transform={`rotate(90 ${W - 8} ${padT + plotH / 2})`}
      >gal / day</text>

      {/* Day-total bars behind (right Y scale, low opacity) */}
      {days.map((d, di) => {
        const total = d.total || 0;
        if (total <= 0) return null;
        const x = padL + di * dayW + 4;
        const y = yScaleDay(total);
        const bh = padT + plotH - y;
        return (
          <g key={`dt${di}`}>
            <title>{`${d.label}: ${total.toFixed(1)} gal total`}</title>
            <rect
              x={x} y={y}
              width={dayW - 8} height={Math.max(0, bh)}
              fill="#6fdc8c" fillOpacity="0.18" rx={3}
            />
          </g>
        );
      })}

      {/* Day-boundary vertical separators + labels */}
      {days.map((d, di) => (
        <g key={`db${di}`}>
          {di > 0 && (
            <line
              x1={padL + di * dayW} x2={padL + di * dayW}
              y1={padT} y2={padT + plotH}
              stroke="currentColor" strokeOpacity="0.15"
            />
          )}
          <text
            x={padL + di * dayW + dayW / 2}
            y={padT + plotH + 14}
            fontSize={10} textAnchor="middle"
            fill="currentColor" fillOpacity="0.7"
          >
            {d.label.length > 6 ? d.label.slice(0, 3) : d.label}
          </text>
          <text
            x={padL + di * dayW + dayW / 2}
            y={padT + plotH + 24}
            fontSize={9} textAnchor="middle"
            fill="#6fdc8c" fillOpacity="0.75"
          >
            {d.total > 0 ? `${d.total.toFixed(0)}g` : ""}
          </text>
        </g>
      ))}

      {/* Hourly bars in front (left Y scale) */}
      {hourly.map((b, i) => {
        const x = padL + i * barW + 0.5;
        if (b.future === true || b.gallons == null) {
          return (
            <rect
              key={i}
              x={x} y={padT + plotH - 1.5}
              width={Math.max(0.6, barW - 0.6)} height={1.5}
              fill="currentColor" fillOpacity={0.10}
            />
          );
        }
        const y = yScaleHour(b.gallons);
        const bh = padT + plotH - y;
        return (
          <rect
            key={i}
            x={x} y={y}
            width={Math.max(0.6, barW - 0.6)}
            height={Math.max(0, bh)}
            fill="#6cd1ff"
          />
        );
      })}

      {/* X-axis line */}
      <line
        x1={padL} x2={W - padR}
        y1={padT + plotH} y2={padT + plotH}
        stroke="currentColor" strokeOpacity="0.35"
      />
    </svg>
  );
}

// -------------- Top-level widget ------------------------------------------

export default function DabPumpHistoryWidget({ data }) {
  const [view, setView] = useState("hour");
  const [dayOffset, setDayOffset] = useState(0);
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const daysHourly = data.days_hourly || [];
  const maxOffset = Math.max(0, daysHourly.length - 1);
  const clampedOffset = Math.min(dayOffset, maxOffset);
  const selectedDay = daysHourly[clampedOffset] || null;
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
                <span className="muted" style={{ fontSize: 11 }}>Day total</span>
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

      {view === "hour"
        ? <DayChart buckets={selectedDay?.by_hour || []} />
        : <WeekChart daysHourly={daysHourly} byDay={data.by_day || []} />}

      {view === "day" && (
        <div className="dab-hist-legend">
          <span className="dab-hist-legend-swatch" style={{ background: "#6cd1ff" }} />
          <span>gal / hour (thin bars)</span>
          <span className="dab-hist-legend-swatch" style={{ background: "rgba(111,220,140,0.35)" }} />
          <span>gal / day (wide overlay)</span>
        </div>
      )}

      {data.collected_hours != null && data.collected_hours < 168 && (
        <div className="muted" style={{ fontSize: 10 }}>
          Home Assistant has only {data.collected_hours < 24
            ? `${Math.round(data.collected_hours)}h`
            : `${Math.round(data.collected_hours / 24)}d`}
          {" "}of history for this sensor so far — earlier hours look empty until more data arrives.
        </div>
      )}
    </div>
  );
}
