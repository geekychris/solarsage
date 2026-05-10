import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function AppliancesPanel({ siteId }) {
  const [appliances, setAppliances] = useState([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [newApp, setNewApp] = useState({ name: "", watts: 1000, typical_minutes: 60, can_defer: 1 });

  async function load() {
    try {
      const r = await api.listAppliances(siteId);
      setAppliances(r.appliances || []);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (siteId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  async function update(a, patch) {
    setBusy(true);
    try {
      await api.upsertAppliance({ ...a, ...patch, site_id: siteId });
      await load();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  async function del(id) {
    if (!confirm("Delete this appliance?")) return;
    setBusy(true);
    try {
      await api.deleteAppliance(id, siteId);
      await load();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  async function addNew() {
    if (!newApp.name) return;
    setBusy(true);
    try {
      await api.upsertAppliance({ ...newApp, site_id: siteId });
      setNewApp({ name: "", watts: 1000, typical_minutes: 60, can_defer: 1 });
      await load();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h3 style={{ margin: 0 }}>Appliances</h3>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Enable what you actually have. The scheduler only recommends windows for enabled, deferrable appliances.
      </div>
      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
      <table className="appliance-table">
        <thead>
          <tr>
            <th></th>
            <th>Name</th>
            <th>Watts</th>
            <th>Run min</th>
            <th>Defer?</th>
            <th>Pref window</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {appliances.map((a) => (
            <tr key={a.id} style={{ opacity: a.enabled ? 1 : 0.5 }}>
              <td>
                <input
                  type="checkbox"
                  checked={!!a.enabled}
                  onChange={(e) => update(a, { enabled: e.target.checked ? 1 : 0 })}
                  disabled={busy}
                />
              </td>
              <td>
                <input
                  value={a.name}
                  onChange={(e) => update(a, { name: e.target.value })}
                  style={{ width: 200 }}
                />
              </td>
              <td>
                <input
                  type="number"
                  value={a.watts}
                  onChange={(e) => update(a, { watts: Number(e.target.value) })}
                  style={{ width: 70 }}
                />
              </td>
              <td>
                <input
                  type="number"
                  value={a.typical_minutes}
                  onChange={(e) => update(a, { typical_minutes: Number(e.target.value) })}
                  style={{ width: 60 }}
                />
              </td>
              <td>
                <input
                  type="checkbox"
                  checked={!!a.can_defer}
                  onChange={(e) => update(a, { can_defer: e.target.checked ? 1 : 0 })}
                />
              </td>
              <td>
                <input
                  type="number"
                  placeholder="—"
                  value={a.preferred_start_hour ?? ""}
                  onChange={(e) => update(a, { preferred_start_hour: e.target.value === "" ? null : Number(e.target.value) })}
                  style={{ width: 40 }}
                />
                <span className="muted">→</span>
                <input
                  type="number"
                  placeholder="—"
                  value={a.preferred_end_hour ?? ""}
                  onChange={(e) => update(a, { preferred_end_hour: e.target.value === "" ? null : Number(e.target.value) })}
                  style={{ width: 40 }}
                />
              </td>
              <td><button onClick={() => del(a.id)}>×</button></td>
            </tr>
          ))}
          <tr style={{ borderTop: "2px solid var(--border)" }}>
            <td></td>
            <td>
              <input
                placeholder="New appliance"
                value={newApp.name}
                onChange={(e) => setNewApp({ ...newApp, name: e.target.value })}
              />
            </td>
            <td>
              <input
                type="number"
                value={newApp.watts}
                onChange={(e) => setNewApp({ ...newApp, watts: Number(e.target.value) })}
                style={{ width: 70 }}
              />
            </td>
            <td>
              <input
                type="number"
                value={newApp.typical_minutes}
                onChange={(e) => setNewApp({ ...newApp, typical_minutes: Number(e.target.value) })}
                style={{ width: 60 }}
              />
            </td>
            <td>
              <input
                type="checkbox"
                checked={!!newApp.can_defer}
                onChange={(e) => setNewApp({ ...newApp, can_defer: e.target.checked ? 1 : 0 })}
              />
            </td>
            <td className="muted">—</td>
            <td><button className="primary" onClick={addNew}>+</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
