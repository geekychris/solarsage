import React, { useState } from "react";

function KV({ obj }) {
  if (!obj) return <div className="empty">No data.</div>;
  const entries = Object.entries(obj)
    .filter(([k]) => !k.startsWith("_") && k !== "battery_units")
    .sort(([a], [b]) => a.localeCompare(b));
  return (
    <table className="kv-table">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td>{k}</td>
            <td>{renderValue(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderValue(v) {
  if (v === null || v === undefined) return <span className="muted">—</span>;
  if (typeof v === "object") return <code>{JSON.stringify(v)}</code>;
  return String(v);
}

export default function RawDataTable({ snapshot }) {
  const [tab, setTab] = useState("runtime");
  if (!snapshot) return <div className="empty">No snapshot yet.</div>;

  const tabs = [
    { id: "runtime", label: "Runtime" },
    { id: "energy", label: "Energy" },
    { id: "battery", label: "Battery" },
    { id: "units", label: `Battery Units (${snapshot.battery?.battery_units?.length || 0})` },
  ];

  return (
    <div>
      <div className="tabs">
        {tabs.map((t) => (
          <div
            key={t.id}
            className={`tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </div>
        ))}
      </div>
      {tab === "runtime" && <KV obj={snapshot.runtime} />}
      {tab === "energy" && <KV obj={snapshot.energy} />}
      {tab === "battery" && <KV obj={snapshot.battery} />}
      {tab === "units" && (
        <div>
          {(snapshot.battery?.battery_units || []).map((u, i) => (
            <div key={i} style={{ marginBottom: 14 }}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
                Unit {u.batIndex ?? i} — SN {u.batterySn || "—"}
              </div>
              <KV obj={u} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
