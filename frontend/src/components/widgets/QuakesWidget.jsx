import React from "react";

function timeAgo(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function magClass(m) {
  if (m >= 5) return "quake-big";
  if (m >= 4) return "quake-med";
  return "quake-small";
}

export default function QuakesWidget({ data }) {
  if (!data) return <div className="muted">No quake data yet.</div>;
  const events = data.events || [];
  if (events.length === 0) {
    return (
      <div className="muted">
        No quakes ≥ M2.5 in the last 24h within {data.radius_km} km.
      </div>
    );
  }
  return (
    <div className="quakes">
      {events.slice(0, 8).map((e) => (
        <div key={e.id} className="quake-row">
          <span className={`quake-mag ${magClass(e.magnitude)}`}>
            M{e.magnitude.toFixed(1)}
          </span>
          <span className="quake-place">{e.place}</span>
          <span className="muted" style={{ fontSize: 11 }}>
            {e.distance_km} km · {timeAgo(e.time_iso)}
          </span>
        </div>
      ))}
      {events.length > 8 && (
        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          + {events.length - 8} more
        </div>
      )}
    </div>
  );
}
