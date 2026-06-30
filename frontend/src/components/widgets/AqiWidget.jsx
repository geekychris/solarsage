import React from "react";

function aqiClass(cat) {
  return {
    "good": "aqi-good",
    "moderate": "aqi-mod",
    "unhealthy for sensitive": "aqi-usg",
    "unhealthy": "aqi-bad",
    "very unhealthy": "aqi-vbad",
    "hazardous": "aqi-haz",
  }[cat] || "muted";
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric" });
}

export default function AqiWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const c = data.current || {};
  const peak = data.peak_24h || {};
  const dust = data.peak_dust_24h || {};
  return (
    <div className="aqi">
      <div className="aqi-now">
        <div className={`aqi-big ${aqiClass(c.category)}`}>
          {c.us_aqi ?? "—"}
        </div>
        <div>
          <div style={{ fontWeight: 600 }}>{c.category}</div>
          <div className="muted" style={{ fontSize: 12 }}>
            PM2.5 {c.pm25?.toFixed?.(0) ?? "—"} · PM10 {c.pm10?.toFixed?.(0) ?? "—"} · O₃ {c.ozone?.toFixed?.(0) ?? "—"}
          </div>
        </div>
      </div>
      <div className="aqi-row">
        <span className="muted">Next 24h peak</span>
        <span className={aqiClass(peak.category)}>
          {peak.us_aqi ?? "—"} ({peak.category})
        </span>
        <span className="muted">at {formatTime(peak.time)}</span>
      </div>
      {dust.ugm3 != null && dust.ugm3 > 50 && (
        <div className="aqi-row">
          <span className="muted">Dust peak</span>
          <span>{Math.round(dust.ugm3)} µg/m³</span>
          <span className="muted">at {formatTime(dust.time)}</span>
        </div>
      )}
    </div>
  );
}
