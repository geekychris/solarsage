import React, { useState } from "react";
import { api } from "../../api.js";

function fmtCountdown(seconds) {
  if (!seconds || seconds <= 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function DabPumpControlWidget({ data, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");

  if (!data) return <div className="muted">Loading…</div>;

  async function trigger(action, value) {
    setBusy(action);
    setErr("");
    try {
      await api.dabPumpControl({ action, value });
      if (onChanged) await onChanged();
    } catch (ex) {
      setErr(ex.message || `${action} failed`);
    } finally {
      setBusy(null);
    }
  }

  const ps = data.active_mode === "power_shower";
  const sleepActive = data.sleep_mode_on;
  const psCountdown = fmtCountdown(data.power_shower_countdown_s);
  const sleepCountdown = fmtCountdown(data.sleep_countdown_s);

  return (
    <div className="dab-control">
      {err && <div className="error-inline">{err}</div>}

      <div className="dab-mode-buttons">
        <button
          type="button"
          className={`dab-mode-btn dab-ps ${ps ? "active" : ""}`}
          disabled={busy != null}
          onClick={() => trigger(ps ? "power_shower_stop" : "power_shower_start")}
          title={ps ? "Stop Power Shower now" : "Start Power Shower now"}
        >
          <div className="dab-mode-icon">🚿</div>
          <div className="dab-mode-name">Power Shower</div>
          <div className="dab-mode-sub">
            {ps ? (psCountdown ? `${psCountdown} left · tap to stop` : "on · tap to stop")
                : "tap to start"}
          </div>
        </button>

        <button
          type="button"
          className={`dab-mode-btn dab-sleep ${sleepActive ? "active" : ""}`}
          disabled={busy != null}
          onClick={() => trigger(sleepActive ? "sleep_off" : "sleep_on")}
          title={sleepActive ? "Disable Sleep mode" : "Enable Sleep mode"}
        >
          <div className="dab-mode-icon">🌙</div>
          <div className="dab-mode-name">Sleep Mode</div>
          <div className="dab-mode-sub">
            {sleepActive
              ? (sleepCountdown ? `${sleepCountdown} left · tap to disable` : "enabled · tap to disable")
              : "tap to enable"}
          </div>
        </button>
      </div>

      <div className="dab-control-detail">
        {(data.options?.power_shower_boost || []).length > 0 && (
          <div className="dab-selector">
            <div className="muted" style={{ fontSize: 11 }}>Power Shower boost</div>
            <div className="dab-chip-row">
              {data.options.power_shower_boost.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className={`dab-chip ${opt === data.power_shower_boost ? "active" : ""}`}
                  disabled={busy != null}
                  onClick={() => trigger("set_boost", opt)}
                >
                  {opt}%
                </button>
              ))}
            </div>
          </div>
        )}

        {(data.options?.sleep_reduction || []).length > 0 && (
          <div className="dab-selector">
            <div className="muted" style={{ fontSize: 11 }}>Sleep pressure reduction</div>
            <div className="dab-chip-row">
              {data.options.sleep_reduction.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className={`dab-chip ${opt === data.sleep_reduction ? "active" : ""}`}
                  disabled={busy != null}
                  onClick={() => trigger("set_reduction", opt)}
                >
                  {opt}%
                </button>
              ))}
            </div>
          </div>
        )}

        {(data.options?.pump_disable || []).length > 0 && (
          <div className="dab-selector">
            <div className="muted" style={{ fontSize: 11 }}>Maintenance</div>
            <div className="dab-chip-row">
              <button
                type="button"
                className="dab-chip dab-chip-warn"
                disabled={busy != null}
                onClick={() => {
                  if (confirm("Disable the pump? No water will flow until re-enabled."))
                    trigger("pump_disable");
                }}
              >
                Disable pump
              </button>
              <button
                type="button"
                className="dab-chip"
                disabled={busy != null}
                onClick={() => trigger("pump_enable")}
              >
                Enable pump
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
