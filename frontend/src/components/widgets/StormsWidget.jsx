import React from "react";

export default function StormsWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const storms = data.active_storms || [];
  const basins = (data.basins_watched || []).join(", ");
  if (storms.length === 0) {
    return (
      <div className="muted">
        No active tropical cyclones in basin{basins.length > 1 ? "s" : ""} {basins}.
      </div>
    );
  }
  return (
    <div className="storms">
      {storms.map((s) => (
        <div key={s.id} className="storm-card">
          <div className="storm-head">
            <span className="storm-name">{s.class || ""} {s.name}</span>
            <span className="muted" style={{ fontSize: 12 }}>
              {s.binNumber}
            </span>
          </div>
          <div className="storm-meta">
            {s.intensity != null && (
              <span>{s.intensity} kn</span>
            )}
            {s.pressure != null && (
              <span>{s.pressure} mb</span>
            )}
            {s.movement && <span>{s.movement}</span>}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
            {s.lat?.toFixed?.(1)}, {s.lon?.toFixed?.(1)} · last update {s.last_update}
          </div>
          {s.publicAdvisory && (
            <a href={s.publicAdvisory} target="_blank" rel="noreferrer">
              Public advisory ↗
            </a>
          )}
        </div>
      ))}
    </div>
  );
}
