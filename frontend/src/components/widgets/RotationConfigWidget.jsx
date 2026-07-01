import React, { useEffect, useState, useCallback } from "react";
import { api } from "../../api.js";

// Widget IDs that make sense on a fullscreen glance display. Excludes
// CRUD editors (contacts / todo / shopping / subs) since they need
// keyboard editing.
const GOOD_ROTATION_KINDS = new Set([
  "solar_vitals", "solar_excess", "precool", "consumption_yoy",
  "aqi", "uv_heat", "quakes", "storms",
  "weather", "tides", "marine", "sun_moon", "fishing_window",
  "sea_temp", "whale_season",
  "trip_planner", "border", "currency", "drive_time",
  "return_countdown", "holidays",
  "hoa", "news", "baja_news", "baja_races", "hoa_newsletter",
  "reservations", "property_tax", "quicklinks",
]);

export default function RotationConfigWidget() {
  const [cfg, setCfg] = useState(null);
  const [widgets, setWidgets] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, wl] = await Promise.all([api.getRotation(), api.listWidgets()]);
      setCfg(r.config);
      setWidgets((wl.widgets || []).filter((w) => GOOD_ROTATION_KINDS.has(w.meta.kind)));
      setErr("");
    } catch (ex) {
      setErr(ex.message || "load failed");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (next) => {
    setBusy(true);
    try {
      await api.putRotation(next);
      setCfg(next);
    } catch (ex) {
      setErr(ex.message || "save failed");
    } finally {
      setBusy(false);
    }
  };

  if (err) return <div className="error">{err}</div>;
  if (!cfg) return <div className="muted">Loading…</div>;

  const seq = cfg.sequence || [];
  const move = (i, delta) => {
    const j = i + delta;
    if (j < 0 || j >= seq.length) return;
    const next = seq.slice();
    [next[i], next[j]] = [next[j], next[i]];
    save({ ...cfg, sequence: next });
  };
  const remove = (i) => save({ ...cfg, sequence: seq.filter((_, k) => k !== i) });
  const changeDwell = (i, dwell) => {
    const next = seq.slice();
    next[i] = { ...next[i], dwell_seconds: Math.max(1, Number(dwell) || 1) };
    save({ ...cfg, sequence: next });
  };
  const changeWidget = (i, widget_id) => {
    const next = seq.slice();
    next[i] = { ...next[i], widget_id };
    save({ ...cfg, sequence: next });
  };
  const add = (widget_id) => {
    const dwell = cfg.default_dwell_seconds || 20;
    save({
      ...cfg,
      sequence: [...seq, { widget_id, dwell_seconds: dwell }],
    });
    setPickerOpen(false);
  };

  const launch = () => {
    const url = new URL(window.location.href);
    url.searchParams.set("view", "rotation");
    window.location.href = url.toString();
  };

  const total = seq.reduce((n, it) => n + (it.dwell_seconds || 0), 0);

  return (
    <div className="rotcfg">
      <div className="rotcfg-head">
        <span className="muted" style={{ fontSize: 12 }}>
          {seq.length} step{seq.length === 1 ? "" : "s"} · {total}s cycle
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={launch} className="primary" disabled={seq.length === 0}>
            ▶ Launch fullscreen
          </button>
        </div>
      </div>
      <div className="rotcfg-defaults">
        <label>
          Default dwell (seconds):
          <input
            type="number"
            min="1"
            value={cfg.default_dwell_seconds || 20}
            onChange={(e) => save({ ...cfg, default_dwell_seconds: Math.max(1, Number(e.target.value) || 1) })}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={!!cfg.enabled}
            onChange={(e) => save({ ...cfg, enabled: e.target.checked })}
          />{" "}
          Auto-launch after idle
        </label>
      </div>
      <div className="rotcfg-seq">
        {seq.length === 0 && (
          <div className="muted">
            No steps yet. Add widgets below.
          </div>
        )}
        {seq.map((step, i) => {
          const w = widgets.find((x) => x.id === step.widget_id);
          return (
            <div key={i} className="rotcfg-step">
              <span className="rotcfg-num">{i + 1}</span>
              <select
                value={step.widget_id}
                onChange={(e) => changeWidget(i, e.target.value)}
              >
                {widgets.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.meta.name} ({x.id})
                  </option>
                ))}
                {!widgets.some((x) => x.id === step.widget_id) && (
                  <option value={step.widget_id}>
                    ⚠ unknown: {step.widget_id}
                  </option>
                )}
              </select>
              <input
                type="number"
                min="1"
                value={step.dwell_seconds || 20}
                onChange={(e) => changeDwell(i, e.target.value)}
                title="Dwell seconds"
                style={{ width: 60 }}
              />
              <span className="muted" style={{ fontSize: 10 }}>s</span>
              <button onClick={() => move(i, -1)} disabled={i === 0} title="Move up">↑</button>
              <button onClick={() => move(i, +1)} disabled={i === seq.length - 1} title="Move down">↓</button>
              <button onClick={() => remove(i)} title="Remove">✕</button>
            </div>
          );
        })}
      </div>
      <div className="rotcfg-add">
        {pickerOpen ? (
          <>
            <select
              onChange={(e) => {
                if (e.target.value) add(e.target.value);
              }}
              defaultValue=""
              autoFocus
            >
              <option value="" disabled>Pick a widget to add…</option>
              {widgets.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.meta.name} ({x.id})
                </option>
              ))}
            </select>
            <button onClick={() => setPickerOpen(false)}>Cancel</button>
          </>
        ) : (
          <button onClick={() => setPickerOpen(true)} disabled={busy}>+ Add step</button>
        )}
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        Adding Solar vitals every other step gives it constant visibility
        while other widgets rotate. Same widget can appear multiple times.
      </div>
    </div>
  );
}
