import React from "react";

function prettyRange(start, end) {
  const s = new Date(start + "T00:00:00");
  const e = new Date(end + "T00:00:00");
  const so = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString(undefined, so)} – ${e.toLocaleDateString(undefined, so)}`;
}

export default function BajaRacesWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const events = data.events || [];
  if (events.length === 0) {
    return <div className="muted">No upcoming races.</div>;
  }
  return (
    <div className="races">
      {events.map((e) => (
        <div key={e.id} className={`race-row ${e.status} ${e.in_san_felipe ? "race-sf" : ""}`}>
          <div className="race-title">
            {e.in_san_felipe && <span className="race-star">★</span>}
            {e.name}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {prettyRange(e.start, e.end)}
            {e.status === "upcoming" && ` · in ${e.days_until} days`}
            {e.status === "ongoing" && " · ongoing"}
          </div>
          {e.notes && (
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              {e.notes}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
