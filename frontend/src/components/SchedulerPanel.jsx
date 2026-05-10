import React, { useEffect, useState } from "react";
import { api } from "../api.js";

function fmtStart(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

export default function SchedulerPanel({ serial, siteId }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const r = await api.schedule(serial, siteId);
      setData(r);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (!serial || !siteId) return;
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial, siteId]);

  if (err) return <div className="panel"><div className="error">{err}</div></div>;
  if (!data) return null;
  const recs = data.recommendations || [];
  const viable = recs.filter((r) => r.start_iso);
  const blocked = recs.filter((r) => !r.start_iso);

  return (
    <div className="panel">
      <h3 style={{ margin: 0 }}>Smart load scheduler</h3>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Best windows in the next 48h based on weather forecast + your enabled appliances.
        Configure appliances in the panel below.
      </div>

      <div style={{ marginTop: 12 }}>
        {viable.length === 0 && blocked.length === 0 && (
          <div className="empty">No enabled appliances yet. Add or enable some below.</div>
        )}
        {viable.map((r) => (
          <div key={r.appliance_name} className="sched-row">
            <div className="sched-name">{r.appliance_name}</div>
            <div className="sched-meta">
              <span className="sched-watts">{r.watts_required.toLocaleString()} W · {r.runtime_minutes}min</span>
              <span className="sched-when">→ {fmtStart(r.start_iso)}</span>
              <span className="sched-surplus">avg surplus {Math.round(r.average_surplus_w).toLocaleString()} W</span>
            </div>
          </div>
        ))}
        {blocked.length > 0 && (
          <details style={{ marginTop: 10 }}>
            <summary className="muted" style={{ fontSize: 12, cursor: "pointer" }}>
              {blocked.length} appliances couldn't be scheduled (need more surplus than forecast offers)
            </summary>
            <div style={{ marginTop: 6 }}>
              {blocked.map((r) => (
                <div key={r.appliance_name} className="muted" style={{ fontSize: 12, marginLeft: 12 }}>
                  · {r.appliance_name} ({r.watts_required.toLocaleString()} W) — {r.reason}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
