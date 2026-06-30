import React, { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";

// --- Specialized editors for known config shapes -------------------------

function LoadsEditor({ value, onChange }) {
  const loads = value || [];
  const update = (i, patch) => {
    const next = loads.slice();
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };
  const addLoad = () => {
    onChange([...loads, { name: "New load", kwh: 1.0, enabled: true }]);
  };
  const removeLoad = (i) => {
    onChange(loads.filter((_, idx) => idx !== i));
  };
  return (
    <div className="loads-editor">
      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
        Uncheck loads you don't have. Disabled loads don't show in suggestions.
      </div>
      {loads.map((ld, i) => (
        <div key={i} className="load-edit-row">
          <input
            type="checkbox"
            checked={ld.enabled !== false}
            onChange={(e) => update(i, { enabled: e.target.checked })}
          />
          <input
            type="text"
            value={ld.name || ""}
            placeholder="Load name"
            onChange={(e) => update(i, { name: e.target.value })}
          />
          <input
            type="number"
            step="0.1"
            min="0"
            value={ld.kwh ?? 0}
            onChange={(e) => update(i, { kwh: parseFloat(e.target.value) || 0 })}
            title="kWh per session"
          />
          <span className="muted" style={{ fontSize: 11 }}>kWh</span>
          <button onClick={() => removeLoad(i)} title="Remove">✕</button>
        </div>
      ))}
      <button onClick={addLoad} className="add-load-btn">+ Add load</button>
    </div>
  );
}

function StationsEditor({ value, onChange }) {
  const stations = value || [];
  const update = (i, patch) => {
    const next = stations.slice();
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };
  const add = () => onChange([
    ...stations,
    { id: `station-${stations.length + 1}`, name: "New station",
      lat: 31.0, lon: -114.8 },
  ]);
  const remove = (i) => onChange(stations.filter((_, idx) => idx !== i));
  return (
    <div className="stations-editor">
      {stations.map((s, i) => (
        <div key={i} className="station-edit-row">
          <input
            type="text"
            value={s.name || ""}
            placeholder="Name"
            onChange={(e) => update(i, { name: e.target.value })}
          />
          <input
            type="number"
            step="0.001"
            value={s.lat ?? 0}
            onChange={(e) => update(i, { lat: parseFloat(e.target.value) })}
            title="Latitude"
          />
          <input
            type="number"
            step="0.001"
            value={s.lon ?? 0}
            onChange={(e) => update(i, { lon: parseFloat(e.target.value) })}
            title="Longitude"
          />
          <button onClick={() => remove(i)} title="Remove">✕</button>
        </div>
      ))}
      <button onClick={add} className="add-load-btn">+ Add station</button>
    </div>
  );
}

function PortsEditor({ value, onChange, knownPorts }) {
  const ports = value || [];
  return (
    <div className="ports-editor">
      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
        Comma-separated CBP port_numbers. Common: 250302 Calexico W, 250301
        Calexico E, 250201 Andrade, 260801 San Luis I, 250401 San Ysidro.
      </div>
      <input
        type="text"
        value={ports.join(", ")}
        onChange={(e) => onChange(
          e.target.value.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
        )}
      />
    </div>
  );
}

// --- Generic scalar editor (fallback) -----------------------------------

function ScalarField({ name, value, schema, onChange }) {
  const type = schema?.type;
  if (schema?.enum) {
    return (
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {schema.enum.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  }
  if (type === "boolean") {
    return (
      <input
        type="checkbox"
        checked={!!value}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (type === "number" || type === "integer") {
    return (
      <input
        type="number"
        step={type === "integer" ? 1 : "any"}
        value={value ?? ""}
        onChange={(e) => onChange(
          type === "integer"
            ? parseInt(e.target.value, 10)
            : parseFloat(e.target.value)
        )}
      />
    );
  }
  return (
    <input
      type="text"
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

// --- Modal --------------------------------------------------------------

export default function WidgetSettings({ widget, onClose, onSaved }) {
  const [config, setConfig] = useState(null);
  const [defaultConfig, setDefaultConfig] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.getWidgetConfig(widget.id).then((r) => {
      if (cancelled) return;
      setConfig(r.config || {});
      setDefaultConfig(r.default_config || {});
    }).catch((ex) => setErr(ex.message || "failed to load config"));
    return () => { cancelled = true; };
  }, [widget.id]);

  const save = useCallback(async () => {
    setBusy(true);
    try {
      await api.putWidgetConfig(widget.id, config);
      onSaved();
      onClose();
    } catch (ex) {
      setErr(ex.message || "failed to save");
    } finally {
      setBusy(false);
    }
  }, [widget.id, config, onClose, onSaved]);

  const reset = () => setConfig({ ...defaultConfig });

  const schema = widget.meta.config_schema || {};
  const props = schema.properties || {};

  if (err && !config) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="error">{err}</div>
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }
  if (!config) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="muted">Loading…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>{widget.meta.name} — Settings</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
          {widget.meta.description}
        </div>

        <div className="settings-form">
          {/* Specialized editors first */}
          {"loads" in props && (
            <div className="settings-field">
              <label>Loads</label>
              <LoadsEditor
                value={config.loads}
                onChange={(v) => setConfig({ ...config, loads: v })}
              />
            </div>
          )}
          {"stations" in props && (
            <div className="settings-field">
              <label>Stations</label>
              <StationsEditor
                value={config.stations}
                onChange={(v) => setConfig({ ...config, stations: v })}
              />
            </div>
          )}
          {"port_numbers" in props && (
            <div className="settings-field">
              <label>Port numbers</label>
              <PortsEditor
                value={config.port_numbers}
                onChange={(v) => setConfig({ ...config, port_numbers: v })}
              />
            </div>
          )}

          {/* Generic scalar fields */}
          {Object.entries(props).map(([name, fieldSchema]) => {
            // Skip fields we render with a specialized editor above.
            if (["loads", "stations", "port_numbers", "routes"].includes(name)) return null;
            // Skip fields with complex types (arrays/objects) — show JSON below.
            if (fieldSchema.type === "array" || fieldSchema.type === "object") return null;
            return (
              <div key={name} className="settings-field">
                <label>{name}</label>
                <ScalarField
                  name={name}
                  value={config[name]}
                  schema={fieldSchema}
                  onChange={(v) => setConfig({ ...config, [name]: v })}
                />
                {fieldSchema.description && (
                  <div className="muted" style={{ fontSize: 11 }}>
                    {fieldSchema.description}
                  </div>
                )}
              </div>
            );
          })}

          {/* Raw JSON fallback for fields we don't have a specialized
              editor for (e.g. routes on the drive-time widget). */}
          <details>
            <summary className="muted">Raw config JSON (advanced)</summary>
            <textarea
              value={JSON.stringify(config, null, 2)}
              rows={10}
              onChange={(e) => {
                try {
                  setConfig(JSON.parse(e.target.value));
                  setErr("");
                } catch {
                  setErr("invalid JSON");
                }
              }}
              style={{ width: "100%", fontFamily: "monospace", fontSize: 12 }}
            />
          </details>
        </div>

        {err && <div className="error">{err}</div>}
        <div className="modal-actions">
          <button onClick={reset} title="Restore default config">Reset</button>
          <button onClick={onClose}>Cancel</button>
          <button onClick={save} disabled={busy} className="primary">
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
