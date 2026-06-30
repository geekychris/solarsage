import React from "react";

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function moonIcon(phase) {
  if (phase == null) return "🌑";
  if (phase < 0.03 || phase > 0.97) return "🌑";
  if (phase < 0.22) return "🌒";
  if (phase < 0.28) return "🌓";
  if (phase < 0.47) return "🌔";
  if (phase < 0.53) return "🌕";
  if (phase < 0.72) return "🌖";
  if (phase < 0.78) return "🌗";
  return "🌘";
}

function DayBlock({ label, day }) {
  if (!day) return null;
  return (
    <div className="sun-day">
      <span style={{ fontWeight: 600 }}>{label}</span>
      <span>🌅 {formatTime(day.sunrise)}</span>
      <span>🌇 {formatTime(day.sunset)}</span>
      <span className="muted">
        {day.daylight_hours ? `${day.daylight_hours} h daylight` : ""}
      </span>
    </div>
  );
}

export default function SunMoonWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className="sunmoon">
      <DayBlock label="Today" day={data.today} />
      <DayBlock label="Tomorrow" day={data.tomorrow} />
      {data.moon && (
        <div className="moon-card">
          <span className="moon-icon">{moonIcon(data.moon.phase)}</span>
          <div>
            <div style={{ fontWeight: 600 }}>{data.moon.name}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {data.moon.illumination_pct}% illuminated
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
