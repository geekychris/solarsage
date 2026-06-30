import React from "react";

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    hour: "numeric",
  });
}

export default function MarineWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const hourly = data.hourly || [];
  const now = hourly[0] || {};
  const best = data.best_windows_today || [];
  return (
    <div className="marine">
      <div className="marine-now">
        <div className="marine-tile">
          <span className="muted" style={{ fontSize: 11 }}>Waves</span>
          <span className="marine-big">
            {now.wave_height_m != null ? `${now.wave_height_m.toFixed(2)} m` : "—"}
          </span>
        </div>
        <div className="marine-tile">
          <span className="muted" style={{ fontSize: 11 }}>Wind</span>
          <span className="marine-big">
            {now.wind_kn != null ? `${Math.round(now.wind_kn)} kn` : "—"}
          </span>
          {now.wind_gust_kn != null && (
            <span className="muted" style={{ fontSize: 11 }}>
              gust {Math.round(now.wind_gust_kn)}
            </span>
          )}
        </div>
        <div className="marine-tile">
          <span className="muted" style={{ fontSize: 11 }}>SST</span>
          <span className="marine-big">
            {now.sst_c != null ? `${now.sst_c.toFixed(1)}°C` : "—"}
          </span>
          {now.sst_c != null && (
            <span className="muted" style={{ fontSize: 11 }}>
              {(now.sst_c * 9 / 5 + 32).toFixed(0)}°F
            </span>
          )}
        </div>
      </div>
      {best.length > 0 && (
        <div className="marine-best">
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            Best fishing windows today
          </div>
          {best.map((b, i) => (
            <div key={i} className="marine-best-row">
              <span style={{ fontWeight: 600 }}>{formatTime(b.time)}</span>
              <span className="muted">
                {b.wave_height_m?.toFixed?.(1) ?? "?"} m ·
                {" "}{Math.round(b.wind_kn || 0)} kn ·
                {" "}{b.sst_c != null ? `${b.sst_c.toFixed(1)}°C` : "?"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
