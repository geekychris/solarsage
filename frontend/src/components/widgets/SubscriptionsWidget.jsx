import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../../api.js";

const OPS = [">", ">=", "<", "<=", "==", "!=", "contains", "not_contains", "changed"];
const CHANNELS = ["tts", "telegram"];

// Suggested condition paths per widget kind. When the user picks a
// widget from the dropdown while creating a new rule, we pre-fill the
// condition + message so they don't have to remember JSON paths.
// (User can edit anything after; when EDITING an existing rule the
// dropdown just swaps widget_id without clobbering.)
const WIDGET_EXAMPLES = {
  aqi:              { path: "current.us_aqi",              op: ">",  value: 100, msg: "AQI is {current.us_aqi} ({current.category})" },
  uv_heat:          { path: "today.peak_uv.value",         op: ">=", value: 8,   msg: "UV peak {today.peak_uv.value} at {today.peak_uv.time}" },
  quakes:           { path: "events[0].magnitude",         op: ">=", value: 4,   msg: "M{events[0].magnitude} quake — {events[0].place}" },
  storms:           { path: "active_count",                op: ">",  value: 0,   msg: "{active_count} active tropical storm(s) in {basins_watched}" },
  border:           { path: "ports[0].pov.standard.delay_minutes", op: ">", value: 60, msg: "Border wait {ports[0].pov.standard.delay_minutes} min at {ports[0].port_name}" },
  currency:         { path: "latest.MXN",                  op: "<",  value: 18,  msg: "MXN at {latest.MXN} — weak peso, favorable for USD" },
  weather:          { path: "current.feels_like",          op: ">=", value: 100, msg: "Feels-like {current.feels_like}°F right now" },
  marine:           { path: "best_windows_today[0].wave_height_m", op: "<=", value: 0.3, msg: "Calm seas — {best_windows_today[0].wave_height_m} m at {best_windows_today[0].time}" },
  fishing_window:   { path: "best_windows[0].score",       op: ">=", value: 75,  msg: "Great fishing window at {best_windows[0].time} (score {best_windows[0].score})" },
  tides:            { path: "stations[0].extremes[0].height_m", op: "<=", value: -1.5, msg: "Very low tide {stations[0].extremes[0].height_m} m at {stations[0].extremes[0].iso}" },
  sea_temp:         { path: "current_c",                   op: ">=", value: 28,  msg: "Sea temp {current_c}°C — {swim_comfort}" },
  precool:          { path: "today.recommend_precool",     op: "==", value: true, msg: "Pre-cool today {today.precool_window[0]} onward" },
  solar_excess:     { path: "today.estimated_excess_kwh",  op: ">=", value: 20,  msg: "{today.estimated_excess_kwh} kWh of surplus today — great time to run loads" },
  property_tax:     { path: "days_until_due",              op: "<=", value: 14,  msg: "Property tax due in {days_until_due} days ({due_this_year})" },
  return_countdown: { path: "days_remaining",              op: "<=", value: 3,   msg: "Return trip in {days_remaining} days" },
  consumption_yoy:  { path: "delta_pct",                   op: ">=", value: 30,  msg: "Using {delta_pct}% more today than same day last year" },
};

function blankRule() {
  return {
    id: undefined,
    widget_id: "",
    name: "",
    message: "",
    enabled: true,
    cooldown_minutes: 60,
    condition: { path: "", op: ">", value: "" },
    actions: [{ type: "tts" }],
  };
}

function ruleFromInitial(initial, widgets) {
  if (!initial) {
    // Fresh add — start on the first widget with a template we know
    const wid = widgets[0]?.id || "";
    const ex = WIDGET_EXAMPLES[wid];
    return {
      ...blankRule(),
      widget_id: wid,
      name: wid ? `${widgets[0].meta.name} alert` : "",
      condition: ex ? { path: ex.path, op: ex.op, value: String(ex.value) }
                    : { path: "", op: ">", value: "" },
      message: ex?.msg || "",
    };
  }
  return {
    id: initial.id,
    widget_id: initial.widget_id,
    name: initial.rule?.name || "",
    message: initial.rule?.message || "",
    enabled: initial.rule?.enabled ?? true,
    cooldown_minutes: initial.rule?.cooldown_minutes ?? 60,
    condition: initial.rule?.condition || { path: "", op: ">", value: "" },
    actions: initial.rule?.actions || [{ type: "tts" }],
  };
}

function RuleForm({ initial, widgets, onSave, onCancel }) {
  const isEdit = !!initial;
  const [rule, setRule] = useState(() => ruleFromInitial(initial, widgets));
  const [busy, setBusy] = useState(false);
  // Track whether the user has hand-edited a field. If they haven't,
  // switching the widget dropdown replaces that field with the new
  // widget's example. If they have, we leave it alone.
  const touched = useRef({ path: !!initial, op: !!initial, value: !!initial,
                            message: !!initial, name: !!initial });

  const changeWidget = (newId) => {
    const wname = widgets.find((w) => w.id === newId)?.meta?.name || newId;
    const ex = WIDGET_EXAMPLES[newId];
    const next = { ...rule, widget_id: newId };
    if (isEdit) { setRule(next); return; }
    if (!touched.current.name)    next.name    = ex ? `${wname} alert` : rule.name;
    if (!touched.current.message) next.message = ex?.msg || "";
    if (!touched.current.path || !touched.current.op || !touched.current.value) {
      next.condition = {
        path:  touched.current.path  ? rule.condition.path  : (ex?.path || ""),
        op:    touched.current.op    ? rule.condition.op    : (ex?.op   || ">"),
        value: touched.current.value ? rule.condition.value : String(ex?.value ?? ""),
      };
    }
    setRule(next);
  };

  const setCond = (patch) => {
    for (const k of Object.keys(patch)) touched.current[k] = true;
    setRule({ ...rule, condition: { ...rule.condition, ...patch } });
  };
  const setField = (field, v) => {
    touched.current[field] = true;
    setRule({ ...rule, [field]: v });
  };
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

  const currentExample = WIDGET_EXAMPLES[rule.widget_id];

  return (
    <div className="sub-form">
      <div className="sub-form-row">
        <label>Name</label>
        <input value={rule.name}
               onChange={(e) => setField("name", e.target.value)}
               placeholder="e.g. AQI is unhealthy" />
      </div>
      <div className="sub-form-row">
        <label>Widget</label>
        <select value={rule.widget_id} onChange={(e) => changeWidget(e.target.value)}>
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
            placeholder={currentExample?.path || "path.into.data"}
          />
          <select value={rule.condition.op}
                  onChange={(e) => setCond({ op: e.target.value })}>
            {OPS.map((o) => <option key={o}>{o}</option>)}
          </select>
          <input
            style={{ flex: 1 }}
            value={rule.condition.value ?? ""}
            onChange={(e) => setCond({ value: e.target.value })}
            placeholder={String(currentExample?.value ?? "value")}
          />
        </div>
      </div>
      <div className="sub-form-row">
        <label>Message</label>
        <input
          value={rule.message}
          onChange={(e) => setField("message", e.target.value)}
          placeholder={currentExample?.msg || "e.g. {some.path} in {other.path}"}
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
  const [err, setErr] = useState(null);

  const doTest = async () => {
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const r = await onTest(sub.id);
      setResult(r);
    } catch (ex) {
      setErr(ex?.message || String(ex) || "test failed");
    } finally {
      setBusy(false);
    }
  };

  // Auto-clear the last test result / error after a bit so the card
  // doesn't fill up with old text.
  useEffect(() => {
    if (!result && !err) return;
    const id = setTimeout(() => { setResult(null); setErr(null); }, 15_000);
    return () => clearTimeout(id);
  }, [result, err]);

  const allOk = result?.results?.every((r) => r.ok);

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
        {err && (
          <div className="sub-test-result sub-test-err">
            test failed → {err}
          </div>
        )}
        {result && !err && (
          <div className={`sub-test-result ${allOk ? "sub-test-ok" : "sub-test-warn"}`}>
            {allOk ? "✓ test fired: " : "⚠ test result: "}
            {(result.results || []).map((r) =>
              `${r.channel}: ${r.ok ? "ok" : r.detail}`
            ).join("; ") || "no actions configured"}
            {result.message && (
              <div className="muted" style={{ fontSize: 10 }}>
                message: "{result.message}"
              </div>
            )}
          </div>
        )}
      </div>
      <div className="sub-actions">
        <button
          onClick={doTest}
          disabled={busy}
          title="Fire actions now (bypasses condition + cooldown)"
          className={busy ? "sub-test-busy" : ""}
        >
          {busy ? "sending…" : "🔔 Test"}
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
          // key forces a fresh mount when switching between add/edit
          key={editing.new ? "new" : `edit-${editing.sub?.id}`}
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
