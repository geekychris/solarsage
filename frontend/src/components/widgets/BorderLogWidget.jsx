import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function LogRow({ c, onEdit, onDelete }) {
  return (
    <div className={`border-log-row dir-${c.direction}`}>
      <div className="log-date">{c.date}</div>
      <div className="log-arrow">
        {c.direction === "us_to_mx" ? "🇺🇸→🇲🇽" : c.direction === "mx_to_us" ? "🇲🇽→🇺🇸" : "?"}
      </div>
      <div className="log-body">
        <div style={{ fontSize: 13 }}>
          {c.port || "?"}
          {c.wait_min != null && ` · ${c.wait_min} min`}
        </div>
        {c.notes && (
          <div className="muted" style={{ fontSize: 11 }}>{c.notes}</div>
        )}
      </div>
      <div className="log-actions">
        <button onClick={onEdit}>✎</button>
        <button onClick={onDelete}>✕</button>
      </div>
    </div>
  );
}

function LogForm({ initial, onSave, onCancel }) {
  const [c, setC] = useState(initial || {
    date: new Date().toISOString().slice(0, 10),
    direction: "us_to_mx",
    port: "Calexico West",
    wait_min: 0,
    purpose: "",
    notes: "",
  });
  return (
    <div className="border-log-form">
      <input type="date" value={c.date} onChange={(e) => setC({ ...c, date: e.target.value })} />
      <select value={c.direction} onChange={(e) => setC({ ...c, direction: e.target.value })}>
        <option value="us_to_mx">US → MX</option>
        <option value="mx_to_us">MX → US</option>
      </select>
      <input placeholder="Port" value={c.port || ""} onChange={(e) => setC({ ...c, port: e.target.value })} />
      <input
        type="number" min="0" placeholder="Wait min"
        value={c.wait_min ?? ""}
        onChange={(e) => setC({ ...c, wait_min: parseInt(e.target.value, 10) || 0 })}
      />
      <input placeholder="Purpose" value={c.purpose || ""} onChange={(e) => setC({ ...c, purpose: e.target.value })} />
      <textarea rows={2} placeholder="Notes" value={c.notes || ""} onChange={(e) => setC({ ...c, notes: e.target.value })} />
      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <button onClick={onCancel}>Cancel</button>
        <button onClick={() => onSave(c)} className="primary">Save</button>
      </div>
    </div>
  );
}

export default function BorderLogWidget({ data }) {
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const saveAll = useCallback(async (crossings) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("border_log");
      await api.putWidgetConfig("border_log", { ...cur.config, crossings });
    } finally {
      setBusy(false);
    }
  }, []);

  if (!data) return <div className="muted">Loading…</div>;
  const crossings = data.crossings || [];
  const stats = data.stats || {};

  const handleSave = async (c) => {
    let next;
    if (editing.new) next = [...crossings, c];
    else {
      next = crossings.slice();
      next[editing.index] = c;
    }
    await saveAll(next);
    setEditing(null);
  };
  const handleDelete = async (i) => {
    if (!confirm("Delete this crossing?")) return;
    await saveAll(crossings.filter((_, idx) => idx !== i));
  };

  return (
    <div className="border-log">
      <div className="border-log-stats">
        <span>{stats.this_year || 0} this year</span>
        <span className="muted">· {stats.total || 0} total</span>
        {stats.avg_wait_min != null && (
          <span className="muted">· avg {stats.avg_wait_min} min</span>
        )}
        <button
          onClick={() => setEditing({ new: true })}
          disabled={busy || editing !== null}
          style={{ marginLeft: "auto" }}
        >
          + Log crossing
        </button>
      </div>
      {editing && (
        <LogForm
          initial={editing.new ? null : crossings[editing.index]}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}
      <div className="border-log-list">
        {crossings.length === 0 && (
          <div className="muted">No crossings logged yet.</div>
        )}
        {crossings.map((c, i) => (
          <LogRow
            key={i}
            c={c}
            onEdit={() => setEditing({ index: i })}
            onDelete={() => handleDelete(i)}
          />
        ))}
      </div>
    </div>
  );
}
