import React, { useEffect, useState } from "react";
import { api } from "../../api.js";

function fmtCountdown(seconds) {
  if (!seconds || seconds <= 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// The DAB pump's countdown sensors update on their own schedule (typically
// 5-15 s after the switch/select command lands). Between "user tapped" and
// "HA reports the new countdown", we show an optimistic overlay so the
// button doesn't sit visibly wrong. Cleared once real data catches up, or
// after MAX_OPTIMISTIC_MS as a safety.
const MAX_OPTIMISTIC_MS = 15_000;

export default function DabPumpControlWidget({ data, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [optimistic, setOptimistic] = useState(null); // {sleep_mode_on?, active_mode?}
  const [optimisticAt, setOptimisticAt] = useState(0);

  // Clear the optimistic overlay once server truth matches what we expected,
  // or after the safety timeout so a lagging sensor doesn't strand it forever.
  useEffect(() => {
    if (!optimistic) return;
    if (data) {
      const matches = Object.entries(optimistic).every(
        ([k, v]) => data[k] === v,
      );
      if (matches) {
        setOptimistic(null);
        return;
      }
    }
    const timeSince = Date.now() - optimisticAt;
    if (timeSince >= MAX_OPTIMISTIC_MS) {
      setOptimistic(null);
      return;
    }
    const t = setTimeout(() => setOptimistic({ ...optimistic }), 500);
    return () => clearTimeout(t);
  }, [data, optimistic, optimisticAt]);

  if (!data) return <div className="muted">Loading…</div>;

  async function trigger(action, value) {
    // Guess what the sensor state should look like once HA catches up.
    const expected = {};
    if (action === "sleep_on")            expected.sleep_mode_on = true;
    if (action === "sleep_off")           expected.sleep_mode_on = false;
    if (action === "power_shower_start")  expected.active_mode = "power_shower";
    if (action === "power_shower_stop")   {
      expected.active_mode = data.sleep_mode_on ? "sleep" : null;
    }
    if (Object.keys(expected).length) {
      setOptimistic(expected);
      setOptimisticAt(Date.now());
    }
    setBusy(action);
    setErr("");
    try {
      await api.dabPumpControl({ action, value });
      if (onChanged) await onChanged();
      // Countdown sensors update ~5-10 s late. Poll again so we catch up
      // without user having to tap Refresh.
      setTimeout(() => { onChanged && onChanged(); }, 3000);
      setTimeout(() => { onChanged && onChanged(); }, 8000);
    } catch (ex) {
      setOptimistic(null);
      setErr(ex.message || `${action} failed`);
    } finally {
      setBusy(null);
    }
  }

  const effectiveSleepOn =
    optimistic?.sleep_mode_on ?? data.sleep_mode_on;
  const effectiveActiveMode =
    optimistic?.active_mode !== undefined
      ? optimistic.active_mode
      : data.active_mode;

  const ps = effectiveActiveMode === "power_shower";
  const sleepActive = !!effectiveSleepOn;
  const psCountdown = fmtCountdown(data.power_shower_countdown_s);
  const sleepCountdown = fmtCountdown(data.sleep_countdown_s);
  const pending = busy != null || optimistic != null;

  return (
    <div className="dab-control">
      {err && <div className="error-inline">{err}</div>}

      <div className="dab-mode-buttons">
        <button
          type="button"
          className={`dab-mode-btn dab-ps ${ps ? "active" : ""} ${pending && optimistic?.active_mode !== undefined ? "pending" : ""}`}
          disabled={busy != null}
          onClick={() => trigger(ps ? "power_shower_stop" : "power_shower_start")}
          title={ps ? "Stop Power Shower now" : "Start Power Shower now"}
        >
          <div className="dab-mode-icon">🚿</div>
          <div className="dab-mode-name">Power Shower</div>
          <div className="dab-mode-sub">
            {optimistic?.active_mode === "power_shower" && !data.power_shower_countdown_s
              ? "starting…"
              : ps
                ? (psCountdown ? `${psCountdown} left · tap to stop` : "on · tap to stop")
                : "tap to start"}
          </div>
        </button>

        <button
          type="button"
          className={`dab-mode-btn dab-sleep ${sleepActive ? "active" : ""} ${pending && optimistic?.sleep_mode_on !== undefined ? "pending" : ""}`}
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
