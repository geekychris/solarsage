import React, { useEffect, useState } from "react";

function useTick(ms = 1000) {
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((x) => x + 1), ms);
    return () => clearInterval(id);
  }, [ms]);
}

function fmtMinutes(totalSec) {
  if (totalSec < 0) return "past";
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

function fmtClock(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric", minute: "2-digit",
  });
}

export default function SunsetWidget({ data }) {
  useTick(1000);
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const now = new Date();
  const sunset = data.sunset ? new Date(data.sunset) : null;
  const goldenStart = data.golden_start ? new Date(data.golden_start) : null;
  const dusk = data.civil_dusk ? new Date(data.civil_dusk) : null;
  const nextSunset = data.next_sunset ? new Date(data.next_sunset) : null;

  // Pick the next relevant target
  let showSunset = sunset;
  if (sunset && now > dusk) showSunset = nextSunset;

  const targetSec = showSunset
    ? Math.max(0, Math.round((showSunset - now) / 1000))
    : 0;
  const isGolden = goldenStart && sunset && now >= goldenStart && now <= sunset;
  const isDusk   = sunset && dusk && now > sunset && now <= dusk;

  const label = isGolden
    ? "Golden hour ends in"
    : isDusk
      ? "Civil dusk in"
      : showSunset === nextSunset
        ? "Tomorrow's sunset in"
        : "Sunset in";

  const targetIso = isGolden ? data.sunset : isDusk ? data.civil_dusk : data.sunset;

  return (
    <div className="sunset-widget">
      <div className={`sunset-headline ${isGolden ? "golden" : ""} ${isDusk ? "dusk" : ""}`}>
        <div className="sunset-label">{label}</div>
        <div className="sunset-big">{fmtMinutes(targetSec)}</div>
        <div className="sunset-target-clock muted">
          at {fmtClock(targetIso)}
        </div>
      </div>

      <div className="sunset-row muted" style={{ fontSize: 12 }}>
        <div>🌅 Sunrise <strong>{fmtClock(data.sunrise)}</strong></div>
        <div>🌇 Sunset  <strong>{fmtClock(data.sunset)}</strong></div>
        <div>🌆 Dusk    <strong>{fmtClock(data.civil_dusk)}</strong></div>
      </div>

      {goldenStart && sunset && now < sunset && !isGolden && (
        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          Golden 20 window begins {fmtClock(data.golden_start)}
        </div>
      )}
    </div>
  );
}
