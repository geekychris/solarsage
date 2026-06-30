import React from "react";

export default function DriveTimeWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className="drive">
      {(data.routes || []).map((r) => (
        <div key={r.id} className="drive-row">
          <span style={{ fontWeight: 600 }}>{r.label}</span>
          {r.ok ? (
            <span className="muted">
              {r.distance_km} km · {(r.duration_min / 60).toFixed(1)} h
            </span>
          ) : (
            <span className="error-inline">{r.error}</span>
          )}
        </div>
      ))}
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        {data.note}
      </div>
    </div>
  );
}
