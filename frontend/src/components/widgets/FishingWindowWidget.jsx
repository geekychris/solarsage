import React from "react";

function formatHour(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric" });
}

function scoreClass(s) {
  if (s >= 75) return "fish-great";
  if (s >= 50) return "fish-good";
  if (s >= 25) return "fish-ok";
  return "fish-poor";
}

export default function FishingWindowWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note && (!data.best_windows || data.best_windows.length === 0)) {
    return <div className="muted">{data.note}</div>;
  }
  const windows = data.best_windows || [];
  const hourly = data.hourly || [];
  return (
    <div className="fishing">
      <div className="muted" style={{ fontSize: 12 }}>
        Station: <strong>{data.station}</strong>{" "}
        · 🌅 {formatHour(data.sunrise)} 🌇 {formatHour(data.sunset)}
      </div>
      {windows.length > 0 && (
        <div className="fishing-best">
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            Top windows today
          </div>
          {windows.map((w, i) => (
            <div key={i} className={`fishing-row ${scoreClass(w.score)}`}>
              <span style={{ fontWeight: 600 }}>{formatHour(w.time)}</span>
              <span className="fish-score">{w.score}</span>
              <span className="muted">
                {w.tide_rate_m_per_h?.toFixed?.(2) ?? "?"} m/h
                {w.wave_height_m != null && ` · ${w.wave_height_m.toFixed(1)} m`}
                {w.wind_kn != null && ` · ${Math.round(w.wind_kn)} kn`}
              </span>
            </div>
          ))}
        </div>
      )}
      {hourly.length > 0 && (
        <details>
          <summary className="muted" style={{ fontSize: 11 }}>
            Hourly score (24h)
          </summary>
          <div className="fishing-hourly">
            {hourly.map((h, i) => (
              <div
                key={i}
                className={`fishing-spark ${scoreClass(h.score)}`}
                style={{ height: `${Math.max(4, h.score / 2)}px` }}
                title={`${formatHour(h.time)} · ${h.score}`}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
