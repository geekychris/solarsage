import React, { useEffect, useState } from "react";
import { api } from "../api.js";

function LiveValue({ live, unit }) {
  if (!live) {
    return <span className="ha-live-missing">not found in HA</span>;
  }
  const stale = false; // could compute from last_updated
  return (
    <span className={`ha-live ${stale ? "stale" : ""}`}>
      <strong>{live.state}</strong>{live.unit ? ` ${live.unit}` : ""}
      {live.friendly_name && (
        <span className="muted" style={{ marginLeft: 6 }}>
          — {live.friendly_name}
        </span>
      )}
    </span>
  );
}

function EntityPicker({ value, domain, onPick }) {
  const [q, setQ] = useState(value || "");
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setQ(value || ""); }, [value]);

  async function search(text) {
    setBusy(true);
    try {
      const r = await api.searchHaEntities(text, domain);
      setHits(r.entities || []);
      setOpen(true);
    } catch {}
    finally { setBusy(false); }
  }

  return (
    <div className="ha-picker">
      <input
        value={q}
        placeholder={domain ? `${domain}.…` : "entity_id"}
        onChange={(e) => {
          setQ(e.target.value);
          if (e.target.value.length >= 2) search(e.target.value);
        }}
        onFocus={() => q.length >= 2 && search(q)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && hits.length > 0 && (
        <div className="ha-picker-dropdown">
          {hits.slice(0, 15).map((h) => (
            <div
              key={h.entity_id}
              className="ha-picker-hit"
              onMouseDown={() => {
                setQ(h.entity_id);
                setOpen(false);
                onPick(h.entity_id);
              }}
            >
              <div><strong>{h.entity_id}</strong></div>
              <div className="muted" style={{ fontSize: 11 }}>
                {h.friendly_name || "—"} · {h.state}{h.unit ? ` ${h.unit}` : ""}
              </div>
            </div>
          ))}
        </div>
      )}
      {busy && <span className="ha-picker-busy">…</span>}
    </div>
  );
}

function RoomSensorEditor({ widgetId, onSaved }) {
  const [config, setConfig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.getWidgetConfig(widgetId).then((r) =>
      setConfig(r.config || {})
    ).catch((ex) => setErr(ex.message));
  }, [widgetId]);

  if (!config) return <div className="muted">Loading room sensors…</div>;
  const sensors = config.room_sensors || [];

  function updateSensor(i, patch) {
    const next = sensors.map((s, j) => j === i ? { ...s, ...patch } : s);
    setConfig({ ...config, room_sensors: next });
  }
  function addSensor() {
    setConfig({
      ...config,
      room_sensors: [
        ...sensors,
        { name: "", temp_entity: "", humidity_entity: "" },
      ],
    });
  }
  function removeSensor(i) {
    setConfig({
      ...config,
      room_sensors: sensors.filter((_, j) => j !== i),
    });
  }

  async function save() {
    setBusy(true); setErr(""); setMsg("");
    try {
      await api.putWidgetConfig(widgetId, config);
      setMsg("Saved.");
      if (onSaved) await onSaved();
    } catch (ex) {
      setErr(ex.message || "save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="room-sensors">
      <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
        Room sensors — any number, any name, temp and/or humidity per row.
      </div>
      {sensors.length === 0 && (
        <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
          None yet — click <strong>Add sensor</strong>.
        </div>
      )}
      {sensors.map((s, i) => (
        <div key={i} className="room-sensor-row">
          <input
            className="room-sensor-name"
            placeholder="Name (e.g. Living)"
            value={s.name || ""}
            onChange={(e) => updateSensor(i, { name: e.target.value })}
          />
          <div className="room-sensor-picker">
            <div className="muted" style={{ fontSize: 10 }}>Temperature</div>
            <EntityPicker
              value={s.temp_entity || ""}
              domain="sensor"
              onPick={(v) => updateSensor(i, { temp_entity: v })}
            />
          </div>
          <div className="room-sensor-picker">
            <div className="muted" style={{ fontSize: 10 }}>Humidity</div>
            <EntityPicker
              value={s.humidity_entity || ""}
              domain="sensor"
              onPick={(v) => updateSensor(i, { humidity_entity: v })}
            />
          </div>
          <button
            type="button"
            className="room-sensor-remove"
            onClick={() => removeSensor(i)}
            title="Remove sensor"
          >✕</button>
        </div>
      ))}
      <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
        <button type="button" onClick={addSensor}>+ Add sensor</button>
        <div style={{ flex: 1 }} />
        {err && <div className="error-inline">{err}</div>}
        {msg && <span className="muted" style={{ color: "var(--ok)" }}>{msg}</span>}
        <button
          type="button" className="primary"
          disabled={busy}
          onClick={save}
        >{busy ? "Saving…" : "Save room sensors"}</button>
      </div>
    </div>
  );
}

function WidgetCard({ card, onSaved }) {
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const editable = card.entities.filter((e) => !e.read_only);
  const readOnly = card.entities.filter((e) => e.read_only);
  const dirty = Object.keys(drafts).length > 0;

  async function save() {
    setSaving(true); setErr(""); setMsg("");
    try {
      await api.putHaIntegration(card.widget_id, drafts);
      setMsg("Saved.");
      setDrafts({});
      if (onSaved) await onSaved();
    } catch (ex) {
      setErr(ex.message || "save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ha-card">
      <div className="ha-card-head">
        <strong>{card.widget_name}</strong>
        <span className="muted"> · {card.widget_id}</span>
      </div>
      {editable.length > 0 && (
        <table className="ha-table">
          <thead>
            <tr>
              <th>Purpose</th><th>Entity ID</th><th>Live value</th>
            </tr>
          </thead>
          <tbody>
            {editable.map((e) => {
              const current = drafts[e.key] ?? (e.entity_id || "");
              return (
                <tr key={e.key}>
                  <td>
                    {e.label}
                    {e.required && <span className="muted"> *</span>}
                  </td>
                  <td>
                    <EntityPicker
                      value={current}
                      domain={e.domain}
                      onPick={(v) => setDrafts((d) => ({ ...d, [e.key]: v }))}
                    />
                  </td>
                  <td><LiveValue live={e.live} unit={e.live?.unit} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {readOnly.length > 0 && (
        <details className="ha-readonly">
          <summary className="muted" style={{ fontSize: 12 }}>
            Derived entities ({readOnly.length}) — read-only, controlled via widget config
          </summary>
          <table className="ha-table">
            <tbody>
              {readOnly.map((e) => (
                <tr key={e.key}>
                  <td>{e.label}</td>
                  <td><code>{e.entity_id}</code></td>
                  <td><LiveValue live={e.live} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      {err && <div className="error-inline">{err}</div>}
      {msg && <div className="muted" style={{ color: "var(--ok)" }}>{msg}</div>}
      {editable.length > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 6 }}>
          <button type="button" disabled={!dirty} onClick={() => setDrafts({})}>
            Revert
          </button>
          <button type="button" className="primary" disabled={!dirty || saving} onClick={save}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      )}
      {card.widget_id === "solar_vitals" && (
        <div style={{ marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          <RoomSensorEditor widgetId="solar_vitals" onSaved={onSaved} />
        </div>
      )}
    </div>
  );
}

export default function HaIntegrationsConfig() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  async function load() {
    try {
      setData(await api.getHaIntegrations());
    } catch (ex) {
      setErr(ex.message);
    }
  }
  useEffect(() => { load(); }, []);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <div className="muted">Loading…</div>;

  const cards = data.integrations || [];
  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        Every Home Assistant entity SolarSage looks at, per widget. Edit
        an entity ID and click Save — the widget refreshes immediately.
        Read-only rows (derived from list config like smart_ac rooms or
        appliances) are shown but not directly editable here.
      </div>
      {cards.length === 0 && (
        <div className="muted">
          No HA integrations declared. Set HA_URL + HA_TOKEN in backend/.env
          and add ha_entities metadata to widgets.
        </div>
      )}
      {cards.map((c) => (
        <WidgetCard key={c.widget_id} card={c} onSaved={load} />
      ))}
    </div>
  );
}
