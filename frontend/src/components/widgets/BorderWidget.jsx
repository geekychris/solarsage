import React from "react";

function delayBadge(info) {
  if (!info) return <span className="muted">—</span>;
  const status = (info.operational_status || "").toLowerCase();
  if (status.includes("closed")) {
    return <span className="border-closed">Closed</span>;
  }
  const mins = info.delay_minutes;
  if (mins == null) {
    return <span className="muted">{info.operational_status || "—"}</span>;
  }
  let cls = "border-fast";
  if (mins >= 60) cls = "border-slow";
  else if (mins >= 20) cls = "border-medium";
  return (
    <span className={cls}>
      {mins} min {info.lanes_open != null ? `· ${info.lanes_open} lanes` : ""}
    </span>
  );
}

export default function BorderWidget({ data }) {
  if (!data || !data.ports) {
    return <div className="muted">No border data yet.</div>;
  }
  if (data.ports.length === 0) {
    return (
      <div className="muted">
        No ports matched the configured port_numbers.
      </div>
    );
  }
  return (
    <table className="border-table">
      <thead>
        <tr>
          <th style={{ textAlign: "left" }}>Crossing</th>
          <th style={{ textAlign: "left" }}>Standard</th>
          <th style={{ textAlign: "left" }}>SENTRI</th>
          <th style={{ textAlign: "left" }}>Ready Lane</th>
        </tr>
      </thead>
      <tbody>
        {data.ports.map((p) => (
          <tr key={p.port_number}>
            <td>
              <div>{p.port_name}{p.crossing_name ? ` — ${p.crossing_name}` : ""}</div>
              <div className="muted" style={{ fontSize: 11 }}>
                {p.hours || "hours unknown"} · {p.port_status || "—"}
              </div>
            </td>
            <td>{delayBadge(p.pov?.standard)}</td>
            <td>{delayBadge(p.pov?.nexus_sentri)}</td>
            <td>{delayBadge(p.pov?.ready_lane)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
