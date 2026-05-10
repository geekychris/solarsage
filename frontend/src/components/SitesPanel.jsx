import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const VENDORS = [
  { id: "eg4", label: "EG4 (monitor.eg4electronics.com)" },
  { id: "solaredge", label: "SolarEdge (monitoringapi.solaredge.com)" },
  { id: "qcell", label: "Q.Cells (stub — tell us the portal)" },
];

function AddSiteForm({ onAdded }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    id: "site-2",
    name: "",
    vendor: "solaredge",
    lat: 31.025, lon: -114.838, tz: "America/Tijuana",
    peak_kw: 10, battery_capacity_kwh: 14.3, max_charge_kw: 8,
    eg4_username: "", eg4_password: "",
    se_api_key: "", se_site_id: "",
    qc_portal: "",
  });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function up(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit(e) {
    e.preventDefault();
    setErr(""); setBusy(true);
    const body = {
      id: form.id, name: form.name, vendor: form.vendor,
      lat: Number(form.lat), lon: Number(form.lon), tz: form.tz,
      peak_kw: Number(form.peak_kw),
      battery_capacity_kwh: Number(form.battery_capacity_kwh),
      max_charge_kw: Number(form.max_charge_kw),
      credentials_json: {},
      config_json: {},
    };
    if (form.vendor === "eg4") {
      body.credentials_json = { username: form.eg4_username, password: form.eg4_password };
    } else if (form.vendor === "solaredge") {
      body.credentials_json = { api_key: form.se_api_key, site_id: form.se_site_id };
    } else if (form.vendor === "qcell") {
      body.config_json = { portal: form.qc_portal };
    }
    try {
      await api.upsertSite(body);
      onAdded?.();
      setOpen(false);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) return <button onClick={() => setOpen(true)} className="primary">+ Add site</button>;

  return (
    <form onSubmit={submit} style={{ marginTop: 12, padding: 12, background: "var(--panel-2)", borderRadius: 8 }}>
      {err && <div className="error" style={{ marginBottom: 8 }}>{err}</div>}
      <div className="grid-2">
        <div className="field"><label>Site ID</label>
          <input value={form.id} onChange={(e) => up("id", e.target.value)} required /></div>
        <div className="field"><label>Display name</label>
          <input value={form.name} onChange={(e) => up("name", e.target.value)} required /></div>
        <div className="field" style={{ gridColumn: "span 2" }}><label>Vendor</label>
          <select value={form.vendor} onChange={(e) => up("vendor", e.target.value)}>
            {VENDORS.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
          </select></div>
        <div className="field"><label>Latitude</label>
          <input value={form.lat} onChange={(e) => up("lat", e.target.value)} /></div>
        <div className="field"><label>Longitude</label>
          <input value={form.lon} onChange={(e) => up("lon", e.target.value)} /></div>
        <div className="field" style={{ gridColumn: "span 2" }}><label>Timezone (IANA)</label>
          <input value={form.tz} onChange={(e) => up("tz", e.target.value)} /></div>
        <div className="field"><label>Peak kW DC</label>
          <input value={form.peak_kw} onChange={(e) => up("peak_kw", e.target.value)} /></div>
        <div className="field"><label>Battery kWh</label>
          <input value={form.battery_capacity_kwh} onChange={(e) => up("battery_capacity_kwh", e.target.value)} /></div>
      </div>

      {form.vendor === "eg4" && (
        <div className="grid-2" style={{ marginTop: 8 }}>
          <div className="field"><label>EG4 username</label>
            <input value={form.eg4_username} onChange={(e) => up("eg4_username", e.target.value)} /></div>
          <div className="field"><label>EG4 password</label>
            <input type="password" value={form.eg4_password} onChange={(e) => up("eg4_password", e.target.value)} /></div>
        </div>
      )}
      {form.vendor === "solaredge" && (
        <div className="grid-2" style={{ marginTop: 8 }}>
          <div className="field"><label>SolarEdge API key</label>
            <input value={form.se_api_key} onChange={(e) => up("se_api_key", e.target.value)} />
            <span className="muted" style={{ fontSize: 11 }}>
              Generate at monitoring.solaredge.com → Admin → Site Access → API Access
            </span>
          </div>
          <div className="field"><label>SolarEdge Site ID</label>
            <input value={form.se_site_id} onChange={(e) => up("se_site_id", e.target.value)} /></div>
        </div>
      )}
      {form.vendor === "qcell" && (
        <div className="field" style={{ marginTop: 8 }}>
          <label>Which Q.Cells portal? (Q.OMMAND, Enphase Enlighten, Sungrow…)</label>
          <input value={form.qc_portal} onChange={(e) => up("qc_portal", e.target.value)} />
          <span className="muted" style={{ fontSize: 11 }}>
            We'll wire up the right backend once we know the portal.
          </span>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
        <button type="button" onClick={() => setOpen(false)}>Cancel</button>
        <button type="submit" className="primary" disabled={busy}>{busy ? "Saving…" : "Save site"}</button>
      </div>
    </form>
  );
}

export default function SitesPanel({ selected, onSelect, refreshKey }) {
  const [sites, setSites] = useState([]);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const r = await api.listSites();
      setSites(r.sites || []);
      setErr("");
      // Auto-select first site if nothing is selected
      if (!selected && (r.sites || []).length > 0) onSelect?.(r.sites[0].id);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  async function del(id) {
    if (!confirm(`Delete site ${id}? (data is preserved)`)) return;
    await api.deleteSite(id, false);
    await load();
  }

  return (
    <div className="panel">
      <h3 style={{ margin: 0 }}>Sites</h3>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Manage multiple solar systems across vendors and locations.
      </div>
      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}
      <div style={{ marginTop: 10 }}>
        {sites.map((s) => (
          <div
            key={s.id}
            className={`inverter-item ${s.id === selected ? "active" : ""}`}
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
            onClick={() => onSelect?.(s.id)}
          >
            <div>
              <div style={{ fontWeight: 600 }}>{s.name}</div>
              <div className="muted" style={{ fontSize: 11 }}>
                {s.vendor.toUpperCase()} · {s.lat.toFixed(2)}, {s.lon.toFixed(2)} · {s.peak_kw} kW
              </div>
            </div>
            <button onClick={(e) => { e.stopPropagation(); del(s.id); }} style={{ fontSize: 11 }}>×</button>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 10 }}>
        <AddSiteForm onAdded={load} />
      </div>
    </div>
  );
}
