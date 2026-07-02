import React from "react";

export default function BirdMigrationWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const active = data.active || [];
  const peaking = data.peaking || [];

  return (
    <div className="bird-mig">
      <div className="muted" style={{ fontSize: 11 }}>
        In {data.month_name}
      </div>
      <div className="bird-summary">
        <div>
          <span className="bird-big">{active.length}</span>
          <span className="muted"> active</span>
        </div>
        {peaking.length > 0 && (
          <div>
            <span className="bird-big">{peaking.length}</span>
            <span className="muted"> peaking</span>
          </div>
        )}
      </div>
      <table className="bird-table">
        <tbody>
          {active.map((row) => (
            <tr key={row.species} className={row.at_peak ? "bird-peak" : ""}>
              <td>
                {row.at_peak && "★ "}
                <strong>{row.species}</strong>
                <div className="muted" style={{ fontSize: 11 }}>
                  {row.note}
                </div>
              </td>
              <td className="muted" style={{ whiteSpace: "nowrap", fontSize: 11 }}>
                {row.direction}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
