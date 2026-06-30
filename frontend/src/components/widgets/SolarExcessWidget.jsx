import React from "react";

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric" });
}

function cloudBadge(cloud) {
  if (cloud == null) return null;
  let cls = "cloud-clear";
  let label = "clear";
  if (cloud >= 80)      { cls = "cloud-overcast"; label = "overcast"; }
  else if (cloud >= 50) { cls = "cloud-cloudy";   label = "cloudy"; }
  else if (cloud >= 25) { cls = "cloud-partly";   label = "partly cloudy"; }
  return <span className={`cloud-pill ${cls}`}>☁ {Math.round(cloud)}% · {label}</span>;
}

export default function SolarExcessWidget({ data }) {
  if (!data || !data.today) return <div className="muted">Loading…</div>;
  const t = data.today;
  return (
    <div className="excess">
      <div className="excess-context">
        {cloudBadge(t.cloud_mean_pct)}
        {t.sunshine_hours != null && (
          <span className="muted" style={{ fontSize: 12 }}>
            ☀ {t.sunshine_hours} h sun
          </span>
        )}
      </div>
      <div className="excess-stats">
        <div className="excess-tile">
          <span className="muted" style={{ fontSize: 11 }}>Production</span>
          <span className="excess-big">{t.estimated_production_kwh} kWh</span>
        </div>
        <div className="excess-tile">
          <span className="muted" style={{ fontSize: 11 }}>Excess</span>
          <span className="excess-big highlight">{t.estimated_excess_kwh} kWh</span>
        </div>
        <div className="excess-tile">
          <span className="muted" style={{ fontSize: 11 }}>To grid</span>
          <span className="excess-big">{t.surplus_to_grid_kwh} kWh</span>
        </div>
      </div>
      {t.best_surplus_window && t.best_surplus_window.length > 0 && (
        <div className="muted" style={{ fontSize: 12 }}>
          Best window:{" "}
          {formatTime(t.best_surplus_window[0])}
          {" – "}
          {formatTime(t.best_surplus_window[t.best_surplus_window.length - 1])}
        </div>
      )}
      <div className="excess-loads">
        <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
          {(data.suggested_loads || []).length === 0
            ? "No loads enabled — open Settings to add some."
            : "Suggested loads (fits in today's surplus)"}
        </div>
        {(data.suggested_loads || []).map((ld, i) => (
          <div key={i} className={`excess-load ${ld.fits ? "fits" : "noroom"}`}>
            <span>{ld.fits ? "✓" : "✗"}</span>
            <span>{ld.name}</span>
            <span className="muted">{ld.kwh} kWh</span>
          </div>
        ))}
      </div>
    </div>
  );
}
