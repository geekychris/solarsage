import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import RotationConfigWidget from "./widgets/RotationConfigWidget.jsx";
import NotificationsConfig from "./NotificationsConfig.jsx";
import HaIntegrationsConfig from "./HaIntegrationsConfig.jsx";

const TABS = [
  { id: "system", label: "System" },
  { id: "rotation", label: "Rotation" },
  { id: "notifications", label: "Notifications" },
  { id: "ha", label: "HA Integrations" },
];

export default function Settings({ open, onClose, onSaved }) {
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState("system");

  useEffect(() => {
    if (!open) return;
    (async () => {
      try {
        setS(await api.settings());
      } catch (ex) {
        setErr(ex.message);
      }
    })();
  }, [open]);

  if (!open) return null;
  if (!s) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="muted">Loading…</div>
        </div>
      </div>
    );
  }

  function up(k, v) {
    setS((cur) => ({ ...cur, [k]: v }));
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const out = await api.updateSettings({
        lat: Number(s.lat),
        lon: Number(s.lon),
        tz: s.tz,
        peak_kw: Number(s.peak_kw),
        battery_capacity_kwh: Number(s.battery_capacity_kwh),
        max_charge_kw: Number(s.max_charge_kw),
        history_days: Number(s.history_days),
      });
      onSaved(out);
      onClose();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`settings-tab ${active === t.id ? "active" : ""}`}
              onClick={() => setActive(t.id)}
            >
              {t.label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <button
            type="button"
            className="settings-tab-close"
            onClick={onClose}
            title="Close"
          >✕</button>
        </div>

        {active === "system" && (
          <form onSubmit={save}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Used by the forecast and clear-sky models. Tune to match your install.
            </div>
            {err && <div className="error">{err}</div>}
            <div className="grid-2">
              <div className="field">
                <label>Latitude (north +)</label>
                <input value={s.lat} onChange={(e) => up("lat", e.target.value)} />
              </div>
              <div className="field">
                <label>Longitude (east +)</label>
                <input value={s.lon} onChange={(e) => up("lon", e.target.value)} />
              </div>
              <div className="field" style={{ gridColumn: "span 2" }}>
                <label>Timezone (IANA name)</label>
                <input value={s.tz} onChange={(e) => up("tz", e.target.value)} placeholder="America/Tijuana" />
                <span className="muted" style={{ fontSize: 11 }}>
                  current UTC offset: {s.tz_offset_minutes} min
                </span>
              </div>
              <div className="field">
                <label>System peak (kW DC)</label>
                <input value={s.peak_kw} onChange={(e) => up("peak_kw", e.target.value)} />
              </div>
              <div className="field">
                <label>Inverter max charge (kW)</label>
                <input value={s.max_charge_kw} onChange={(e) => up("max_charge_kw", e.target.value)} />
              </div>
              <div className="field">
                <label>Battery capacity (kWh)</label>
                <input value={s.battery_capacity_kwh} onChange={(e) => up("battery_capacity_kwh", e.target.value)} />
              </div>
              <div className="field">
                <label>History window (days)</label>
                <input value={s.history_days} onChange={(e) => up("history_days", e.target.value)} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button type="button" onClick={onClose}>Cancel</button>
              <button className="primary" type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        )}

        {active === "rotation" && (
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Pick which widgets rotate in the fullscreen "screensaver" view
              and how long each is shown. Same widget can appear multiple
              times to weight its visibility (e.g. Solar vitals every other
              step).
            </div>
            <RotationConfigWidget />
          </div>
        )}

        {active === "notifications" && <NotificationsConfig />}

        {active === "ha" && <HaIntegrationsConfig />}
      </div>
    </div>
  );
}
