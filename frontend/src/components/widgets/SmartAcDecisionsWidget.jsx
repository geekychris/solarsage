import React, { useState } from "react";

const MODE_COLOR = {
  ON_TRACK: "#3fb950",
  SURPLUS: "#58a6ff",
  CHARGE_BEHIND: "#d29922",
  DEFICIT: "#f85149",
  EVENING: "#a371f7",
  NIGHT: "#8b97a8",
};

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtActions(actions) {
  if (!actions || actions.length === 0) return "—";
  return actions
    .map((a) => `${a.action} ${a.room}`)
    .join(", ");
}

function onList(ac_on) {
  if (!ac_on) return [];
  return Object.entries(ac_on)
    .filter(([, v]) => v)
    .map(([k]) => k);
}

function DecisionRow({ decision, expanded, onToggle }) {
  const on = onList(decision.ac_on);
  const rowClass = decision.has_actions
    ? "sad-row sad-row-action"
    : "sad-row";
  return (
    <>
      <div className={rowClass} onClick={onToggle}>
        <div className="sad-time">{fmtTime(decision.ts)}</div>
        <div
          className="sad-mode"
          style={{ color: MODE_COLOR[decision.mode] || "#8b97a8" }}
        >
          {decision.mode}
        </div>
        <div className="sad-soc">
          {decision.soc != null ? `${decision.soc.toFixed(0)}%` : "—"}
        </div>
        <div className="sad-on">
          {on.length ? on.join(", ") : <span className="muted">— none</span>}
        </div>
        <div className="sad-actions">
          {decision.has_actions
            ? <strong>{fmtActions(decision.actions)}</strong>
            : <span className="muted">no change</span>}
        </div>
      </div>
      {expanded && (
        <div className="sad-expanded">
          <div className="sad-metrics">
            <span title="PV power">☀ {decision.pv_power_w?.toFixed(0) || "—"} W</span>
            <span title="Battery power (+ charging)">🔋 {decision.battery_power_w?.toFixed(0) || "—"} W</span>
            <span title="Load">🏠 {decision.load_w?.toFixed(0) || "—"} W</span>
            {decision.outdoor_f != null && (
              <span title="Outdoor">🌡 {decision.outdoor_f}°F</span>
            )}
            {decision.enabled === false && (
              <span style={{ color: "#f85149" }}>disabled</span>
            )}
            {decision.unoccupied && (
              <span style={{ color: "#d29922" }}>unoccupied</span>
            )}
          </div>
          {decision.indoor_f && Object.keys(decision.indoor_f).length > 0 && (
            <div className="sad-indoor">
              indoors:{" "}
              {Object.entries(decision.indoor_f).map(([room, t]) => (
                <span key={room} style={{ marginRight: 8 }}>
                  {room} {t}°F
                </span>
              ))}
            </div>
          )}
          <table className="sad-reasons">
            <tbody>
              {Object.entries(decision.reasons || {}).map(([room, reason]) => {
                const isOn = decision.ac_on?.[room];
                return (
                  <tr key={room}>
                    <td className={isOn ? "sad-room-on" : "sad-room-off"}>
                      {isOn ? "●" : "○"} {room}
                    </td>
                    <td className="sad-reason">{reason}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function SmartAcDecisionsWidget({ data }) {
  const [expanded, setExpanded] = useState(0);  // most-recent expanded by default

  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) {
    return <div className="muted" style={{ fontSize: 12 }}>{data.note}</div>;
  }
  const decisions = data.decisions || [];
  if (decisions.length === 0) {
    return <div className="muted">No decisions logged yet.</div>;
  }

  return (
    <div className="sad">
      <div className="sad-summary">
        <span>
          Latest:{" "}
          <strong style={{ color: MODE_COLOR[data.latest_mode] || "#8b97a8" }}>
            {data.latest_mode}
          </strong>{" "}
          at {fmtDateTime(data.latest_ts)}
        </span>
        <span className="muted">
          {data.latest_soc != null ? `SoC ${data.latest_soc.toFixed(0)}%` : ""}
          {" · "}
          on: {data.on_rooms?.length ? data.on_rooms.join(", ") : "—"}
        </span>
      </div>

      <div className="sad-header">
        <div className="sad-time">time</div>
        <div className="sad-mode">mode</div>
        <div className="sad-soc">SoC</div>
        <div className="sad-on">on</div>
        <div className="sad-actions">actions</div>
      </div>

      <div className="sad-list">
        {decisions.map((d, i) => (
          <DecisionRow
            key={`${d.ts}-${i}`}
            decision={d}
            expanded={expanded === i}
            onToggle={() => setExpanded(expanded === i ? -1 : i)}
          />
        ))}
      </div>

      <div className="muted" style={{ fontSize: 10, marginTop: 6 }}>
        {data.count} rows · click a row to expand · log: {data.log_path}
      </div>
    </div>
  );
}
