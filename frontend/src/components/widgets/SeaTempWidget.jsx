import React from "react";

export default function SeaTempWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className="sea-temp">
      <div className="sea-temp-now">
        <div>
          <div className="sea-big">
            {data.current_c != null ? `${data.current_c.toFixed(1)}°C` : "—"}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            {data.current_f != null ? `${data.current_f}°F` : ""}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 13 }}>{data.swim_comfort}</div>
          <div className="muted" style={{ fontSize: 11 }}>{data.fishing_note}</div>
        </div>
      </div>
      <div className="sea-days">
        {(data.days || []).slice(0, 7).map((d) => (
          <div key={d.date} className="sea-day">
            <div className="muted" style={{ fontSize: 11 }}>
              {new Date(d.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" })}
            </div>
            <div style={{ fontWeight: 600 }}>{d.avg_c}°</div>
            <div className="muted" style={{ fontSize: 10 }}>{d.low_c}–{d.high_c}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
