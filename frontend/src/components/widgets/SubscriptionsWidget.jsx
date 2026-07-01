import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../api.js";

const OPS = [">", ">=", "<", "<=", "==", "!=", "contains", "not_contains", "changed"];
const CHANNELS = ["tts", "telegram"];

function RuleForm({ initial, widgets, onSave, onCancel }) {
  const [rule, setRule] = useState(() => ({
    id: initial?.id,
    widget_id: initial?.widget_id || (widgets[0]?.id || ""),
    name: initial?.rule?.name || "",
    message: initial?.rule?.message || "",
    enabled: initial?.rule?.enabled ?? true,
    cooldown_minutes: initial?.rule?.cooldown_minutes ?? 60,
    condition: initial?.rule?.condition || { path: "", op: ">", value: "" },
    actions: initial?.rule?.actions || [{ type: "tts" }],
  }));
  const [busy, setBusy] = useState(false);

  const setCond = (patch) => setRule({ ...rule, condition: { ...rule.condition, ...patch } });
  const setAction = (i, patch) => {
    const acts = rule.actions.slice();
    acts[i] = { ...acts[i], ...patch };
    setRule({ ...rule, actions: acts });
  };
  const addAction = () => setRule({ ...rule, actions: [...rule.actions, { type: "tts" }] });
  const removeAction = (i) => setRule({
    ...rule, actions: rule.actions.filter((_, idx) => idx !== i),
  });

  const doSave = async () => {
    setBusy(true);
    try {
      const body = {
        id: rule.id,
        widget_id: rule.widget_id,
        name: rule.name,
        message: rule.message,
        enabled: rule.enabled,
        cooldown_minutes: Number(rule.cooldown_minutes) || 0,
        condition: {
          path: rule.condition.path,
          op: rule.condition.op,
          value: _autoParse(rule.condition.value),
        },
        actions: rule.actions,
      };
      await onSave(body);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sub-form">
      <div className="sub-form-row">
        <label>Name</label>
        <input value={rule.name} onChange={(e) => setRule({ ...rule, name: e.target.value })} placeholder="AQI is unhealthy" />
      </div>
      <div className="sub-form-row">
        <label>Widget</label>
        <select value={rule.widget_id} onChange={(e) => setRule({ ...rule, widget_id: e.target.value })}>
          {widgets.map((w) => (
            <option key={w.id} value={w.id}>{w.meta.name} ({w.id})</option>
          ))}
        </select>
      </div>
      <div className="sub-form-row">
        <label>Condition</label>
        <div style={{ display: "flex", gap: 4, flex: 1 }}>
          <input
            style={{ flex: 2 }}
            value={rule.condition.path}
            onChange={(e) => setCond({ path: e.target.value })}
            placeholder="current.us_aqi"
          />
          <select value={rule.condition.op} onChange={(e) => setCond({ op: e.target.value })}>
            {OPS.map((o) => <option key={o}>{o}</option>)}
          </select>
          <input
            style={{ flex: 1 }}
            value={rule.condition.value ?? ""}
            onChange={(e) => setCond({ value: e.target.value })}
            placeholder="100"
          />
        </div>
      </div>
      <div className="sub-form-row">
        <label>Message</label>
        <input
          value={rule.message}
          onChange={(e) => setRule({ ...rule, message: e.target.value })}
          placeholder="AQI is {current.us_aqi} ({current.category})"
        />
      </div>
      <div className="sub-form-row">
        <label>Cooldown (min)</label>
        <input type="number" min="0" value={rule.cooldown_minutes}
          onChange={(e) => setRule({ ...rule, cooldown_minutes: e.target.value })} />
      </div>
      <div className="sub-form-row">
        <label>Enabled</label>
        <input type="checkbox" checked={rule.enabled}
          onChange={(e) => setRule({ ...rule, enabled: e.target.checked })} />
      </div>
      <div>
        <label style={{ fontSize: 12, fontWeight: 600 }}>Actions</label>
        {rule.actions.map((a, i) => (
          <div key={i} className="sub-action-row">
            <select value={a.type || "tts"} onChange={(e) => setAction(i, { type: e.target.value })}>
              {CHANNELS.map((c) => <option key={c}>{c}</option>)}
            </select>
            <input
              placeholder="Optional custom text (else uses rule message)"
              value={a.text || ""}
              onChange={(e) => setAction(i, { text: e.target.value })}
            />
            {a.type === "telegram" && (
              <input
                placeholder="Title (optional)"
                value={a.title || ""}
                onChange={(e) => setAction(i, { title: e.target.value })}
              />
            )}
            <button onClick={() => removeAction(i)}>✕</button>
          </div>
        ))}
        <button onClick={addAction} className="add-load-btn">+ action</button>
      </div>
      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", marginTop: 8 }}>
        <button onClick={onCancel}>Cancel</button>
        <button onClick={doSave} disabled={busy} className="primary">
          {busy ? "…" : "Save"}
        </button>
      </div>
    </div>
  );
}

function _autoParse(v) {
  if (v === "" || v == null) return v;
  const n = Number(v);
  if (!Number.isNaN(n) && String(n) === String(v).trim()) return n;
  if (v === "true") return true;
  if (v === "false") return false;
  return v;
}

function SubRow({ sub, widgets, onEdit, onDelete, onTest }) {
  const w = widgets.find((x) => x.id === sub.widget_id);
  const rule = sub.rule || {};
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const doTest = async () => {
    setBusy(true);
    try {
      const r = await onTest(sub.id);
      setResult(r);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`sub-row ${rule.enabled === false ? "sub-disabled" : ""}`}>
      <div className="sub-body">
        <div className="sub-name">
          {rule.name || "(unnamed)"}
          {rule.enabled === false && <span className="muted"> · off</span>}
        </div>
        <div className="muted" style={{ fontSize: 11 }}>
          {w?.meta.name || sub.widget_id} · {rule.condition?.path} {rule.condition?.op} {String(rule.condition?.value)}
        </div>
        <div className="muted" style={{ fontSize: 11 }}>
          Actions: {(rule.actions || []).map((a) => a.type).join(", ") || "none"}
          {rule.cooldown_minutes ? ` · cooldown ${rule.cooldown_minutes}m` : ""}
        </div>
        {sub.last_fired_at && (
          <div className="muted" style={{ fontSize: 10 }}>
            last fired {new Date(sub.last_fired_at * 1000).toLocaleString()}: {sub.last_result}
          </div>
        )}
        {result && (
          <div className="sub-test-result">
            test → {result.results.map((r) =>
              `${r.channel}: ${r.ok ? "ok" : r.detail}`
            ).join("; ")}
          </div>
        )}
      </div>
      <div className="sub-actions">
        <button onClick={doTest} disabled={busy} title="Fire actions now">
          {busy ? "…" : "🔔 Test"}
        </button>
        <button onClick={() => onEdit(sub)}>✎</button>
        <button onClick={() => onDelete(sub.id)}>✕</button>
      </div>
    </div>
  );
}

export default function SubscriptionsWidget() {
  const [subs, setSubs] = useState(null);
  const [widgets, setWidgets] = useState([]);
  const [editing, setEditing] = useState(null);   // {sub:...} or {new:true}
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, w] = await Promise.all([
        api.listSubscriptions(),
        api.listWidgets(),
      ]);
      setSubs(s.subscriptions || []);
      setWidgets(w.widgets || []);
      setErr("");
    } catch (ex) {
      setErr(ex.message || "load failed");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  const handleSave = async (body) => {
    await api.upsertSubscription(body);
    setEditing(null);
    await load();
  };
  const handleDelete = async (id) => {
    if (!confirm("Delete this subscription?")) return;
    await api.deleteSubscription(id);
    await load();
  };
  const handleTest = (id) => api.testSubscription(id);

  if (err) return <div className="error">{err}</div>;
  if (subs === null) return <div className="muted">Loading…</div>;

  return (
    <div className="subs">
      <div className="subs-head">
        <span className="muted" style={{ fontSize: 12 }}>
          {subs.length} rule{subs.length === 1 ? "" : "s"}
        </span>
        <button
          onClick={() => setEditing({ new: true })}
          disabled={editing !== null}
        >
          + Add rule
        </button>
      </div>
      {editing && (
        <RuleForm
          initial={editing.new ? null : editing.sub}
          widgets={widgets}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}
      <div className="subs-list">
        {subs.length === 0 && !editing && (
          <div className="muted">
            No rules yet. Add one — e.g. "AQI &gt; 100 → tts + telegram".
          </div>
        )}
        {subs.map((s) => (
          <SubRow
            key={s.id}
            sub={s}
            widgets={widgets}
            onEdit={(sub) => setEditing({ sub })}
            onDelete={handleDelete}
            onTest={handleTest}
          />
        ))}
      </div>
    </div>
  );
}
