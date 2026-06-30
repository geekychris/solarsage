import React from "react";

function prettyDate(d) {
  if (!d) return "—";
  return new Date(d + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  });
}

export default function HolidaysWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const upcoming = data.upcoming || [];
  return (
    <div className="holidays">
      {data.next ? (
        <div className="holiday-next">
          <div style={{ fontSize: 13 }}>
            Next: <strong>{data.next.local_name || data.next.name}</strong>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {prettyDate(data.next.date)} ({data.days_until_next} days)
          </div>
        </div>
      ) : (
        <div className="muted">No upcoming holidays found.</div>
      )}
      {upcoming.length > 1 && (
        <details style={{ marginTop: 6 }}>
          <summary className="muted">Upcoming ({upcoming.length})</summary>
          <ul style={{ margin: "6px 0 0 16px" }}>
            {upcoming.slice(1).map((h, i) => (
              <li key={i}>
                <strong>{prettyDate(h.date)}</strong> — {h.local_name || h.name}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
