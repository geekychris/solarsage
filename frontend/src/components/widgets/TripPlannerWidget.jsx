import React from "react";

function prettyDate(d) {
  if (!d) return "—";
  return new Date(d + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

function scoreClass(s) {
  if (s >= 80) return "trip-great";
  if (s >= 60) return "trip-good";
  if (s >= 40) return "trip-ok";
  return "trip-bad";
}

export default function TripPlannerWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const r = data.primary_route || {};
  const total = data.total_trip_min_today;
  return (
    <div className="trip">
      {r.ok && (
        <div className="trip-now">
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Right now</div>
            <div style={{ fontWeight: 600 }}>{r.label}</div>
          </div>
          <div className="trip-now-stats">
            <div>{r.distance_km} km · {Math.round(r.duration_min)} min drive</div>
            <div>
              border wait{" "}
              <strong>
                {data.current_border_wait_min == null ? "?" : data.current_border_wait_min}
              </strong>{" "}min
            </div>
            {total != null && (
              <div style={{ marginTop: 4 }}>
                <strong>total ~{Math.round(total / 60 * 10) / 10} h</strong>
              </div>
            )}
          </div>
        </div>
      )}
      <div className="trip-days">
        {(data.days || []).map((d, i) => (
          <div key={i} className={`trip-day ${scoreClass(d.score)}`}>
            <div style={{ fontSize: 12 }}>{prettyDate(d.date)}</div>
            <div className="trip-score">{Math.round(d.score || 0)}</div>
            <div className="muted" style={{ fontSize: 10 }}>
              {Math.round(d.high || 0)}° · ☁{Math.round(d.cloud_mean_pct || 0)}%
              {d.is_holiday && " · 🎉"}
            </div>
          </div>
        ))}
      </div>
      {data.note && (
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          {data.note}
        </div>
      )}
    </div>
  );
}
