import React from "react";

function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short", month: "short", day: "numeric",
  });
}

function daysLabel(n) {
  if (n === 0) return "tonight";
  if (n === 1) return "tomorrow";
  if (n <= 7) return `in ${n} days`;
  if (n <= 60) return `in ${n} days`;
  const months = Math.round(n / 30);
  return `in ~${months} months`;
}

export default function MeteorShowersWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const next = data.next;
  const upcoming = data.upcoming || [];

  return (
    <div className="meteor-showers">
      {next && (
        <div className={`meteor-hero ${next.within_announce_window ? "soon" : ""}`}>
          <div>
            <div className="muted" style={{ fontSize: 11 }}>Next shower</div>
            <div className="meteor-name">☄ {next.name}</div>
            <div style={{ fontSize: 13 }}>
              peaks {fmtDate(next.peak_date)}
              <span className="muted"> — {daysLabel(next.days_to_peak)}</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              {next.hint}
            </div>
          </div>
          <div className="meteor-zhr">
            <div className="muted" style={{ fontSize: 11 }}>ZHR</div>
            <div className="meteor-zhr-big">{next.zhr}</div>
          </div>
        </div>
      )}
      <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Upcoming
      </div>
      <table className="meteor-table">
        <tbody>
          {upcoming.slice(1, 5).map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td className="muted">{fmtDate(s.peak_date)}</td>
              <td className="muted">ZHR {s.zhr}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
