import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function formatClock(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric", minute: "2-digit",
  });
}

function StateBadge({ state }) {
  const cls = ({
    charging: "sv-charging",
    discharging: "sv-discharging",
    steady: "sv-steady",
  })[state] || "muted";
  const label = ({
    charging: "⚡ Charging",
    discharging: "🔋 Discharging",
    steady: "= Steady",
  })[state] || state || "?";
  return <span className={`sv-state ${cls}`}>{label}</span>;
}

// --------- SVG Pie chart -----------------------------------------------

const PIE_COLORS = [
  "#6cd1ff", "#ffd166", "#6fdc8c", "#ef6f6c",
  "#c54a8c", "#ff9b6c", "#a29bfe", "#00cec9",
];

function LoadPie({ breakdown }) {
  const [hover, setHover] = useState(null);
  const positive = (breakdown || []).filter(
    (b) => !b.negative && b.watts > 5,
  );
  const total = positive.reduce((n, b) => n + b.watts, 0);
  if (total === 0) {
    return <div className="muted" style={{ fontSize: 12 }}>No load right now.</div>;
  }

  const size = 140;
  const cx = size / 2, cy = size / 2, r = size / 2 - 4;
  let a0 = -Math.PI / 2;
  const slices = positive.map((b, i) => {
    const frac = b.watts / total;
    const a1 = a0 + frac * Math.PI * 2;
    const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
    const large = frac > 0.5 ? 1 : 0;
    const d = `M ${cx},${cy} L ${x0.toFixed(1)},${y0.toFixed(1)} A ${r},${r} 0 ${large},1 ${x1.toFixed(1)},${y1.toFixed(1)} Z`;
    const color = b.name === "Unaccounted" ? "#555" : PIE_COLORS[i % PIE_COLORS.length];
    a0 = a1;
    return { d, color, frac, ...b };
  });

  const active = hover != null ? slices[hover] : null;
  const centerBig = active
    ? (active.watts / 1000).toFixed(2)
    : (total / 1000).toFixed(1);
  const centerSub = active
    ? `${Math.round(active.frac * 100)}%`
    : "kW load";

  return (
    <div className="sv-pie-wrap">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="sv-pie">
        {slices.map((s, i) => (
          <path
            key={i}
            d={s.d}
            fill={s.color}
            stroke="#0e1116"
            strokeWidth="1"
            className={`sv-pie-slice ${hover === i ? "hover" : ""} ${hover != null && hover !== i ? "dim" : ""}`}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <title>{`${s.name} — ${(s.watts / 1000).toFixed(2)} kW (${Math.round(s.frac * 100)}%)`}</title>
          </path>
        ))}
        {/* donut hole for the label */}
        <circle cx={cx} cy={cy} r={r * 0.45} fill="var(--panel, #181c22)" pointerEvents="none" />
        <text x={cx} y={cy - 4} textAnchor="middle" fill="currentColor" fontSize="16" fontWeight="700" pointerEvents="none">
          {centerBig}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="#888" fontSize="10" pointerEvents="none">
          {centerSub}
        </text>
      </svg>
      <div className="sv-pie-legend">
        {slices.map((s, i) => (
          <div
            key={i}
            className={`sv-pie-leg-row ${hover === i ? "hover" : ""}`}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="sv-pie-swatch" style={{ background: s.color }} />
            <span className="sv-pie-name">{s.name}</span>
            <span className="muted">{(s.watts / 1000).toFixed(2)} kW</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --------- SVG animated flow diagram ------------------------------------

function FlowDiagram({ data }) {
  const pv = data.solar?.total_kw || 0;
  const charge = data.battery_flow?.charge_kw || 0;
  const discharge = data.battery_flow?.discharge_kw || 0;
  const load = data.load?.kw || 0;
  const toGrid = data.grid?.to_grid_kw || 0;
  const fromGrid = data.grid?.from_grid_kw || 0;
  const soc = data.battery?.soc;

  // Flow animation speed scales with power. Higher power → faster dots.
  const dashLen = 6;
  const dashGap = 6;
  const dur = (kw) => kw < 0.1 ? 0 : Math.max(0.4, 3 / Math.max(0.5, kw));

  return (
    <svg viewBox="0 0 320 180" className="sv-flow" preserveAspectRatio="xMidYMid meet">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5"
                markerWidth="4" markerHeight="4" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
        </marker>
      </defs>

      {/* Nodes */}
      <g className="sv-node sv-node-pv">
        <circle cx="60" cy="40" r="28" />
        <text x="60" y="36" textAnchor="middle">☀</text>
        <text x="60" y="52" textAnchor="middle" className="sv-node-val">{pv.toFixed(1)} kW</text>
      </g>
      <g className="sv-node sv-node-batt">
        <rect x="140" y="110" width="60" height="42" rx="6" ry="6" />
        <text x="170" y="128" textAnchor="middle">🔋</text>
        <text x="170" y="145" textAnchor="middle" className="sv-node-val">
          {soc != null ? `${Math.round(soc)}%` : "—"}
        </text>
      </g>
      <g className="sv-node sv-node-load">
        <circle cx="260" cy="40" r="28" />
        <text x="260" y="36" textAnchor="middle">🏠</text>
        <text x="260" y="52" textAnchor="middle" className="sv-node-val">{load.toFixed(1)} kW</text>
      </g>
      <g className="sv-node sv-node-grid">
        <circle cx="60" cy="140" r="22" />
        <text x="60" y="145" textAnchor="middle">⚡</text>
      </g>

      {/* Edges — animated when active */}
      {pv > 0.1 && (
        <line x1="88" y1="40" x2="230" y2="40"
              className="sv-flow-line-anim sv-flow-solar"
              strokeDasharray={`${dashLen} ${dashGap}`}
              style={{ animationDuration: `${dur(pv)}s` }}
              markerEnd="url(#arrow)"
        />
      )}
      {charge > 0.1 && (
        <line x1="170" y1="60" x2="170" y2="108"
              className="sv-flow-line-anim sv-flow-charge"
              strokeDasharray={`${dashLen} ${dashGap}`}
              style={{ animationDuration: `${dur(charge)}s` }}
              markerEnd="url(#arrow)"
        />
      )}
      {discharge > 0.1 && (
        <line x1="170" y1="108" x2="170" y2="60"
              className="sv-flow-line-anim sv-flow-discharge"
              strokeDasharray={`${dashLen} ${dashGap}`}
              style={{ animationDuration: `${dur(discharge)}s` }}
              markerEnd="url(#arrow)"
        />
      )}
      {toGrid > 0.1 && (
        <line x1="82" y1="122" x2="82" y2="62"
              className="sv-flow-line-anim sv-flow-export"
              strokeDasharray={`${dashLen} ${dashGap}`}
              style={{ animationDuration: `${dur(toGrid)}s` }}
              markerEnd="url(#arrow)"
        />
      )}
      {fromGrid > 0.1 && (
        <line x1="62" y1="118" x2="62" y2="62"
              className="sv-flow-line-anim sv-flow-import"
              strokeDasharray={`${dashLen} ${dashGap}`}
              style={{ animationDuration: `${dur(fromGrid)}s` }}
              markerEnd="url(#arrow)"
        />
      )}
    </svg>
  );
}

// --------- Calibration modal ------------------------------------------

function CalibrationModal({ applianceName, currentLoadKw, onClose, onSaved }) {
  const [baseline, setBaseline] = useState(null);
  const [withOn, setWithOn] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const delta = baseline != null && withOn != null
    ? Math.max(0, withOn - baseline)
    : null;

  const save = async () => {
    if (delta == null) return;
    setBusy(true);
    try {
      await api.calibrateSolarVitals(applianceName, Math.round(delta * 1000));
      onSaved();
      onClose();
    } catch (ex) {
      setErr(ex.message || "save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>Calibrate: {applianceName}</h3>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          Watches the actual house load and computes this appliance's
          consumption from the difference.
        </div>
        <div className="sv-cal-live">
          <span className="muted">Live load:</span>
          <strong>{currentLoadKw != null ? currentLoadKw.toFixed(2) : "—"} kW</strong>
        </div>
        <ol className="sv-cal-steps">
          <li className={baseline != null ? "sv-cal-done" : "sv-cal-current"}>
            <strong>Turn OFF</strong> the appliance if it's on. Wait for the
            load to settle.
            <br />
            <button
              onClick={() => setBaseline(currentLoadKw)}
              disabled={busy || currentLoadKw == null}
              className="primary"
            >
              Record baseline
            </button>
            {baseline != null && (
              <span className="muted"> · baseline = {baseline.toFixed(2)} kW</span>
            )}
          </li>
          <li className={
            baseline == null ? "" :
            withOn != null ? "sv-cal-done" : "sv-cal-current"
          }>
            <strong>Turn ON</strong> the appliance. Wait ~30s for the load
            to stabilise.
            <br />
            <button
              onClick={() => setWithOn(currentLoadKw)}
              disabled={busy || baseline == null || currentLoadKw == null}
              className="primary"
            >
              Record with-on
            </button>
            {withOn != null && (
              <span className="muted"> · with-on = {withOn.toFixed(2)} kW</span>
            )}
          </li>
          {delta != null && (
            <li className="sv-cal-current">
              Delta: <strong>{delta.toFixed(2)} kW</strong>{" "}
              ({Math.round(delta * 1000)} W)
              <br />
              <button
                onClick={save}
                disabled={busy || delta === 0}
                className="primary"
              >
                {busy ? "Saving…" : `Save ${Math.round(delta * 1000)} W`}
              </button>
            </li>
          )}
        </ol>
        {err && <div className="error-inline">{err}</div>}
        <div className="modal-actions">
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

// --------- Appliance quick-toggle + calibration entry ---------------

function ApplianceGrid({ data, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [saveErr, setSaveErr] = useState("");
  const [calibrating, setCalibrating] = useState(null);

  // Prefer the widget's resolved appliance list (with HA state
  // baked in). Falls back to config for backwards compat.
  const appliances = data?.load?.appliances || [];
  const currentLoadKw = data?.load?.kw ?? null;

  const toggleManual = useCallback(async (name) => {
    setBusy(true);
    setSaveErr("");
    try {
      const cur = await api.getWidgetConfig("solar_vitals");
      const items = (cur.config?.appliances || []).map((a) =>
        a.name === name ? { ...a, on: !a.on } : a
      );
      await api.putWidgetConfig("solar_vitals", { ...cur.config, appliances: items });
      if (onChanged) await onChanged();
    } catch (ex) {
      setSaveErr(ex.message || "save failed");
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  return (
    <div className="sv-appliance-panel">
      <div className="muted sv-appliances-hint"
           title="Tap to toggle manual. HA-linked entries auto-update from Home Assistant.">
        What's on now
      </div>
      <div className="sv-appliances">
        {appliances.map((a) => {
          const haLabel = a.ha_entity_id
            ? `HA: ${a.ha_state || "unavailable"}`
            : "manual";
          return (
            <div key={a.name}
                 className={`sv-appliance ${a.on ? "sv-app-on" : ""}`}
                 title={`${a.watts} W · ${haLabel}`}>
              <button
                onClick={() => a.ha_entity_id ? null : toggleManual(a.name)}
                disabled={busy || !!a.ha_entity_id}
                className="sv-app-toggle"
                title={a.ha_entity_id ? "HA-controlled — override in HA" : "Toggle manual"}
              >
                {a.name}
                <span className="muted"> · {(a.watts / 1000).toFixed(1)} kW</span>
                {a.ha_entity_id && <span className="sv-app-ha">🏠</span>}
              </button>
              <button
                onClick={() => setCalibrating(a.name)}
                title="Calibrate — measure actual wattage"
                className="sv-app-cal"
              >⚙</button>
            </div>
          );
        })}
      </div>
      {saveErr && <div className="error-inline">{saveErr}</div>}
      {calibrating && (
        <CalibrationModal
          applianceName={calibrating}
          currentLoadKw={currentLoadKw}
          onClose={() => setCalibrating(null)}
          onSaved={() => onChanged && onChanged()}
        />
      )}
    </div>
  );
}

// --------- smart_ac control grid --------------------------------------

const OVERRIDE_PRESETS = [
  { label: "30 m", minutes: 30 },
  { label: "1 h",  minutes: 60 },
  { label: "2 h",  minutes: 120 },
  { label: "4 h",  minutes: 240 },
];

function SmartAcGrid({ rooms, onChanged }) {
  const [openRoom, setOpenRoom] = useState(null);
  const [duration, setDuration] = useState(60);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function flip(room, nextState, mins) {
    setBusy(true);
    setErr("");
    try {
      await api.smartAcOverride({
        room, state: nextState, duration_minutes: mins,
      });
      if (onChanged) await onChanged();
      setOpenRoom(null);
    } catch (ex) {
      setErr(ex.message || "override failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="sv-smart-ac">
      <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
        Air conditioners — tap a chip to override the smart_ac scheduler.
        Watts are scaled to fit measured load.
      </div>
      <div className="sv-smart-ac-grid">
        {rooms.map((r) => {
          const rated = r.rated_watts;
          const scale = r.scale;
          const title = [
            `${r.entity_id} — ${r.state}`,
            r.note && r.note !== "ok" ? `(${r.note})` : null,
            rated && scale != null && scale < 0.999
              ? `rated ${rated} W · scale ${(scale * 100).toFixed(0)}%`
              : null,
          ].filter(Boolean).join(" · ");
          return (
            <button
              key={r.room}
              type="button"
              className={`sv-smart-ac-chip ${r.on ? "on" : "off"}`}
              title={title}
              disabled={busy}
              onClick={() => {
                setOpenRoom(r.room === openRoom ? null : r.room);
              }}
            >
              <div className="sv-smart-ac-name">{r.name || r.room}</div>
              <div className="sv-smart-ac-watts">
                {r.on ? `${(Number(r.watts) / 1000).toFixed(2)} kW` : "off"}
              </div>
              {r.on && rated && scale != null && scale < 0.999 && (
                <div className="sv-smart-ac-rated">
                  of {(rated / 1000).toFixed(1)} kW rated
                </div>
              )}
            </button>
          );
        })}
      </div>
      {err && <div className="error-inline">{err}</div>}
      {openRoom && (() => {
        const r = rooms.find((x) => x.room === openRoom);
        if (!r) return null;
        const isOn = r.on;
        return (
          <div className="sv-smart-ac-override">
            <div style={{ fontSize: 12, marginBottom: 6 }}>
              Override <strong>{r.name}</strong> — smart_ac will leave it alone
              for the picked window.
            </div>
            <div className="sv-smart-ac-duration">
              {OVERRIDE_PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  className={duration === p.minutes ? "active" : ""}
                  onClick={() => setDuration(p.minutes)}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="sv-smart-ac-actions">
              <button type="button"
                      className="sv-smart-ac-btn danger"
                      disabled={busy}
                      onClick={() => flip(openRoom, "off", duration)}>
                Turn OFF for {duration}m
              </button>
              <button type="button"
                      className="sv-smart-ac-btn primary"
                      disabled={busy}
                      onClick={() => flip(openRoom, "on", duration)}>
                Turn ON for {duration}m
              </button>
              <button type="button"
                      className="sv-smart-ac-btn"
                      disabled={busy}
                      onClick={() => flip(openRoom, isOn ? "on" : "off", 0)}
                      title="Clear the override; smart_ac resumes control on next tick">
                Release to smart_ac
              </button>
              <button type="button"
                      className="sv-smart-ac-btn ghost"
                      onClick={() => setOpenRoom(null)}>
                Cancel
              </button>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// --------- Main component ---------------------------------------------

export default function SolarVitalsWidget({ data, onChanged }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const b = data.battery || {};
  const s = data.solar || {};
  const l = data.load || {};
  const bf = data.battery_flow || {};
  const p = data.projection;
  const wp = data.weather_projection;
  const cb = data.cut_back;
  const today = data.today || {};

  return (
    <div className="sv2">
      <FlowDiagram data={data} />

      <div className="sv2-summary">
        <div className="sv2-tile sv2-batt">
          <div className="sv2-label">Battery</div>
          <div className="sv2-big">{b.soc != null ? Math.round(b.soc) : "—"}%</div>
          <div className="sv2-sub">
            {b.kwh_remaining != null ? `${b.kwh_used?.toFixed(1)} / ${b.capacity_kwh?.toFixed(1)} kWh` : ""}
          </div>
          <div className="sv-soc-bar-outer">
            <div className="sv-soc-bar-inner"
                 style={{ width: `${Math.max(0, Math.min(100, b.soc || 0))}%` }} />
          </div>
        </div>
        <div className="sv2-tile sv2-solar">
          <div className="sv2-label">Solar</div>
          <div className="sv2-big">{s.total_kw != null ? s.total_kw.toFixed(2) : "—"}</div>
          <div className="sv2-sub">kW total</div>
          <div className="sv2-strings">
            {(s.strings || []).map((st) => (
              <span key={st.n} className="sv2-string">
                str{st.n}: <strong>{st.kw.toFixed(2)}</strong>
              </span>
            ))}
          </div>
        </div>
        <div className="sv2-tile sv2-load">
          <div className="sv2-label">Load</div>
          <div className="sv2-big">{l.kw != null ? l.kw.toFixed(2) : "—"}</div>
          <div className="sv2-sub">kW ({l.field || "unknown"})</div>
        </div>
        <div className="sv2-tile sv2-flow">
          <div className="sv2-label">Battery flow</div>
          <StateBadge state={bf.state} />
          <div className="sv2-big" style={{ fontSize: 22, marginTop: 4 }}>
            {bf.state === "charging"    ? `+${bf.charge_kw?.toFixed(2)} kW` :
             bf.state === "discharging" ? `-${bf.discharge_kw?.toFixed(2)} kW` :
             "±0 kW"}
          </div>
        </div>
      </div>

      {Array.isArray(l.room_sensors) && l.room_sensors.length > 0 && (
        <div className="sv-temps">
          {l.room_sensors.map((r, i) => (
            <div key={i} className="sv-temp">
              <div className="sv-temp-label">{r.name || `Sensor ${i + 1}`}</div>
              <div className="sv-temp-value">
                {r.temp_value != null
                  ? `${r.temp_value.toFixed(1)}${r.temp_unit || "°"}`
                  : "—"}
              </div>
              {r.humidity_value != null && (
                <div className="sv-temp-hum">
                  💧 {r.humidity_value.toFixed(0)}{r.humidity_unit || "%"}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {p && (
        <div className={`sv-projection sv-${p.direction}`}>
          <div>
            {p.direction === "charging" ? "🔌 Full" : "🪫 Empty"} in{" "}
            <strong>{p.pretty}</strong>
            <span className="muted"> at {formatClock(p.target_at)}</span>
            <span className="muted" style={{ marginLeft: 8 }}>
              · at current {p.rate_kw} kW
            </span>
          </div>
          {wp && p.direction === "charging" && (
            <div style={{ marginTop: 4, fontSize: 13 }}>
              <span style={{ color: "#3fb950" }}>🌤 Weather-aware:</span>{" "}
              <strong>{wp.pretty}</strong>
              <span className="muted"> at {formatClock(wp.target_at)}</span>
              {wp.pv_per_ghi_w_per_wm2 && (
                <span className="muted" style={{ marginLeft: 8, fontSize: 11 }}>
                  · GHI × {wp.pv_per_ghi_w_per_wm2}
                </span>
              )}
            </div>
          )}
        </div>
      )}
      {cb && (
        <div className="sv-cutback">
          ⚠ Start conserving in <strong>{cb.pretty}</strong>
          <span className="muted"> (~{formatClock(cb.at)}, {cb.target_soc}% left)</span>
        </div>
      )}

      {l.kw != null && l.kw > 0.05 && (
        <div className="sv2-pie-row">
          <LoadPie breakdown={l.breakdown} />
          <ApplianceGrid data={data} onChanged={onChanged} />
        </div>
      )}

      {Array.isArray(l.smart_ac_rooms) && l.smart_ac_rooms.length > 0 && (
        <SmartAcGrid rooms={l.smart_ac_rooms} onChanged={onChanged} />
      )}

      {Object.keys(today).length > 0 && (
        <div className="sv2-today">
          {today.todayYielding    != null && <span>☀ {today.todayYielding.toFixed(1)} kWh</span>}
          {today.todayCharging    != null && <span>🔋+ {today.todayCharging.toFixed(1)} kWh</span>}
          {today.todayDischarging != null && <span>🔋- {today.todayDischarging.toFixed(1)} kWh</span>}
          {today.todayUsage       != null && <span>🏠 {today.todayUsage.toFixed(1)} kWh</span>}
          {today.todayImport      != null && <span>⚡→ {today.todayImport.toFixed(1)} kWh</span>}
        </div>
      )}
    </div>
  );
}
