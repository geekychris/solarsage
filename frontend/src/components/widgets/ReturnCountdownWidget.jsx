import React from "react";

export default function ReturnCountdownWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (!data.return_date) {
    return (
      <div className="muted">
        Set a return date via Settings ⚙ to start the countdown.
      </div>
    );
  }
  const days = data.days_remaining;
  return (
    <div className="return-count">
      <div className="return-days">
        {days == null ? "—" : days > 0 ? days : days === 0 ? "today" : `${-days} days ago`}
      </div>
      {days > 0 && <div className="muted">days until</div>}
      <div style={{ fontWeight: 600, marginTop: 4 }}>{data.label}</div>
      <div className="muted" style={{ fontSize: 12 }}>
        {new Date(data.return_date + "T00:00:00").toLocaleDateString(undefined, {
          weekday: "short", month: "long", day: "numeric", year: "numeric",
        })}
      </div>
    </div>
  );
}
