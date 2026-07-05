import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

export default function PropertyModeWidget({ data, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const setOccupied = useCallback(async (occupied) => {
    setBusy(true); setErr("");
    try {
      await api.propertyModeSet(occupied);
      if (onChanged) await onChanged();
    } catch (ex) {
      setErr(ex.message || "failed");
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (!data) return <div className="muted">Loading…</div>;
  const occupied = data.occupied;
  const modeClass = occupied === true
    ? "mode-occupied"
    : occupied === false
      ? "mode-vacant"
      : "";
  const label = occupied === true
    ? "Occupied 🏠"
    : occupied === false
      ? "Unoccupied 🌵"
      : "Unknown ⚠️";

  return (
    <div className={`property-mode ${modeClass}`}>
      <div className="property-mode-big">{label}</div>

      {occupied === null && (
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          HA didn't respond — is <code>HA_URL</code>/<code>HA_TOKEN</code> set?
        </div>
      )}

      <div className="property-mode-toggle">
        <button
          type="button"
          className={occupied === true ? "active" : ""}
          disabled={busy || occupied === true}
          onClick={() => setOccupied(true)}
        >Occupied 🏠</button>
        <button
          type="button"
          className={occupied === false ? "active" : ""}
          disabled={busy || occupied === false}
          onClick={() => setOccupied(false)}
        >Unoccupied 🌵</button>
      </div>

      {err && <div className="error-inline">{err}</div>}

      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        When Unoccupied, smart_ac runs bake-mitigation only (living room
        prioritized). HA is the source of truth — the toggle above flips{" "}
        {data.ha_entity && <code>{data.ha_entity}</code>}.
      </div>

      {data.ha_ui_url && (
        <div style={{ marginTop: 4 }}>
          <a
            href={data.ha_ui_url}
            target="_blank"
            rel="noreferrer"
            className="property-mode-ha-link"
          >
            Open Home Assistant ↗
          </a>
        </div>
      )}
    </div>
  );
}
