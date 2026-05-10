import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const SEVERITY_COLOR = {
  info: "#58a6ff",
  warn: "#d29922",
  error: "#f85149",
};

export default function AlertsPanel({ siteId }) {
  const [alerts, setAlerts] = useState([]);
  const [err, setErr] = useState("");
  const [unackOnly, setUnackOnly] = useState(false);

  async function load() {
    try {
      const r = await api.listAlerts(siteId, unackOnly);
      setAlerts(r.alerts || []);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (!siteId) return;
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, unackOnly]);

  async function ack(id) {
    await api.ackAlert(id);
    await load();
  }

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Alerts</h3>
        <label style={{ fontSize: 12, color: "var(--muted)", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={unackOnly}
            onChange={(e) => setUnackOnly(e.target.checked)}
            style={{ marginRight: 4 }}
          />
          Unacknowledged only
        </label>
      </div>
      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
      {alerts.length === 0 ? (
        <div className="empty">No alerts. Everything looks fine.</div>
      ) : (
        <div style={{ marginTop: 10 }}>
          {alerts.map((a) => (
            <div key={a.id} className="alert-row" style={{
              borderLeft: `3px solid ${SEVERITY_COLOR[a.severity] || "#444"}`,
              opacity: a.acknowledged ? 0.5 : 1,
            }}>
              <div className="alert-when">{new Date(a.ts).toLocaleString()}</div>
              <div className="alert-text">{a.message}</div>
              <div className="alert-rule muted">rule: {a.rule}</div>
              {!a.acknowledged && (
                <button onClick={() => ack(a.id)} style={{ marginTop: 4, fontSize: 11 }}>
                  Acknowledge
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
