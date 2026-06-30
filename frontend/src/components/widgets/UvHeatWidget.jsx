import React from "react";

function uvLabel(uv) {
  if (uv == null) return ["—", "muted"];
  if (uv >= 11) return [`${uv.toFixed(1)} extreme`, "uv-extreme"];
  if (uv >= 8)  return [`${uv.toFixed(1)} very high`, "uv-high"];
  if (uv >= 6)  return [`${uv.toFixed(1)} high`, "uv-high"];
  if (uv >= 3)  return [`${uv.toFixed(1)} moderate`, "uv-mod"];
  return [`${uv.toFixed(1)} low`, "uv-low"];
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function DayCard({ label, day }) {
  if (!day) return null;
  const [uvText, uvCls] = uvLabel(day.peak_uv?.value);
  return (
    <div className="uv-day">
      <div className="uv-day-head">
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span className="muted" style={{ fontSize: 11 }}>{day.date}</span>
      </div>
      <div className="uv-row">
        <span className="muted">Peak UV</span>
        <span className={uvCls}>{uvText}</span>
        <span className="muted">at {formatTime(day.peak_uv?.time)}</span>
      </div>
      <div className="uv-row">
        <span className="muted">High temp</span>
        <span>{day.high_temp_f != null ? `${Math.round(day.high_temp_f)}°F` : "—"}</span>
      </div>
      <div className="uv-row">
        <span className="muted">Peak feels-like</span>
        <span>
          {day.peak_apparent_f?.value != null
            ? `${Math.round(day.peak_apparent_f.value)}°F at ${formatTime(day.peak_apparent_f.time)}`
            : "—"}
        </span>
      </div>
      {day.any_danger && (
        <div className="uv-danger">
          ⚠ Danger window: {formatTime(day.danger_window_hours[0])}
          {" – "}
          {formatTime(day.danger_window_hours[day.danger_window_hours.length - 1])}
          {" "}({day.danger_window_hours.length} h)
        </div>
      )}
    </div>
  );
}

export default function UvHeatWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className="uv-stack">
      <DayCard label="Today"    day={data.today} />
      <DayCard label="Tomorrow" day={data.tomorrow} />
    </div>
  );
}
