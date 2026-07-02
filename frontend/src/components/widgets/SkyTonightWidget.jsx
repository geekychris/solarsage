import React from "react";

function fmtClock(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric", minute: "2-digit",
  });
}

const PLANET_EMOJI = {
  Mercury: "☿", Venus: "♀", Mars: "♂", Jupiter: "♃", Saturn: "♄",
};

export default function SkyTonightWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;
  const planets = data.planets || [];
  const visible = planets.filter((p) => p.visible);
  const moon = data.moon || {};
  return (
    <div className="sky-tonight">
      <div className="sky-summary">
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Tonight</div>
          <div className="sky-big">
            {visible.length} planet{visible.length === 1 ? "" : "s"}
          </div>
        </div>
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Moon</div>
          <div className="sky-big">
            {moon.illumination_pct?.toFixed(0)}%
            <span className="muted" style={{ fontSize: 12, marginLeft: 6 }}>
              {moon.name}
            </span>
          </div>
        </div>
      </div>
      <table className="sky-table">
        <thead>
          <tr>
            <th></th><th>Rises</th><th>Peak</th><th>Sets</th><th>°alt</th>
          </tr>
        </thead>
        <tbody>
          {planets.map((p) => (
            <tr key={p.planet} className={p.visible ? "" : "sky-below"}>
              <td>
                <strong>{PLANET_EMOJI[p.planet]} {p.planet}</strong>
              </td>
              <td>{fmtClock(p.rises_at)}</td>
              <td>{fmtClock(p.peak_at)}</td>
              <td>{fmtClock(p.sets_at)}</td>
              <td>{p.peak_altitude_deg.toFixed(0)}°</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
