import React from "react";

function prettyDate(d) {
  if (!d) return "—";
  return new Date(d + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

function daysUntil(d) {
  if (!d) return "";
  const target = new Date(d + "T00:00:00");
  const now = new Date();
  const ms = target - now;
  const days = Math.round(ms / 86400000);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days < 0) return `${-days}d ago`;
  return `in ${days}d`;
}

export default function ReservationsWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const upcoming = data.upcoming || [];
  const errors = data.errors || [];
  if (upcoming.length === 0 && errors.length === 0) {
    return (
      <div className="muted">
        No iCal feeds configured — paste Airbnb / Vrbo URLs via Settings.
      </div>
    );
  }
  return (
    <div className="reservations">
      {upcoming.map((r, i) => (
        <div key={i} className="reservation-row">
          <div className="reservation-when">
            <div style={{ fontWeight: 600 }}>{prettyDate(r.start)}</div>
            <div className="muted" style={{ fontSize: 11 }}>
              {daysUntil(r.start)}
            </div>
          </div>
          <div className="reservation-main">
            <div>{r.summary || "(no title)"}</div>
            <div className="muted" style={{ fontSize: 11 }}>
              {r.source}
              {r.end && ` · until ${prettyDate(r.end)}`}
            </div>
          </div>
        </div>
      ))}
      {errors.map((e, i) => (
        <div key={`err-${i}`} className="error-inline">
          {e.source}: {e.error}
        </div>
      ))}
    </div>
  );
}
