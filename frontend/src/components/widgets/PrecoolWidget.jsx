import React from "react";

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric" });
}

function DayBlock({ label, day }) {
  if (!day) return null;
  if (!day.recommend_precool) {
    return (
      <div className="precool-day">
        <div style={{ fontWeight: 600 }}>{label}</div>
        <div className="muted" style={{ fontSize: 12 }}>
          Peak feels-like {Math.round(day.peak_apparent_f || 0)}°F at{" "}
          {formatTime(day.peak_at)} — no pre-cool needed.
        </div>
      </div>
    );
  }
  const w = day.precool_window || [];
  return (
    <div className="precool-day precool-active">
      <div style={{ fontWeight: 600 }}>{label}</div>
      <div className="muted" style={{ fontSize: 12 }}>
        Peak feels-like {Math.round(day.peak_apparent_f)}°F at {formatTime(day.peak_at)}
      </div>
      {w.length > 0 && (
        <div className="precool-window">
          ❄ Pre-cool {formatTime(w[0])} – {formatTime(w[w.length - 1])}
        </div>
      )}
    </div>
  );
}

export default function PrecoolWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className="precool">
      <DayBlock label="Today"    day={data.today} />
      <DayBlock label="Tomorrow" day={data.tomorrow} />
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        Trigger: peak feels-like ≥ {data.trigger_apparent_f}°F
      </div>
    </div>
  );
}
