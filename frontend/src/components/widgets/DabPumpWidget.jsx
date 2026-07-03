import React from "react";

function fmtGal(n) {
  if (n == null) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function fmtCountdown(seconds) {
  if (!seconds || seconds <= 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function DabPumpWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;

  const running = (data.running_count || 0) > 0;
  const modeBadge = (() => {
    if (data.active_mode === "power_shower") {
      const t = fmtCountdown(data.power_shower_countdown_s);
      return <span className="dab-mode dab-mode-ps">🚿 Power Shower{t ? ` · ${t}` : ""}</span>;
    }
    if (data.active_mode === "sleep") {
      const t = fmtCountdown(data.sleep_countdown_s);
      return <span className="dab-mode dab-mode-sleep">🌙 Sleep{t ? ` · ${t}` : ""}</span>;
    }
    return null;
  })();

  const faulted = (data.fault_count || 0) > 0
    || (data.system_status && data.system_status !== "Ok");

  return (
    <div className="dab-pump">
      <div className="dab-hero">
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Pump</div>
          <div className={`dab-status ${running ? "dab-running" : "dab-standby"}`}>
            {running ? "▶ Running" : "◼ Standby"}
          </div>
          {faulted && (
            <div className="dab-fault">⚠ {data.system_status || "fault"}</div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="muted" style={{ fontSize: 11 }}>Pressure</div>
          <div className="dab-big">
            {data.pressure_psi?.toFixed(1) ?? "—"}
            <span className="dab-unit"> psi</span>
          </div>
          {data.setpoint_psi != null && (
            <div className="muted" style={{ fontSize: 11 }}>
              target {data.setpoint_psi.toFixed(1)} psi
            </div>
          )}
        </div>
      </div>

      {modeBadge && <div className="dab-mode-row">{modeBadge}</div>}

      <div className="dab-grid">
        <div className="dab-cell">
          <div className="muted">Flow</div>
          <div className="dab-cell-val">
            {data.flow_gpm != null ? data.flow_gpm.toFixed(1) : "—"}
            <span className="dab-unit"> gpm</span>
          </div>
        </div>
        <div className="dab-cell">
          <div className="muted">Draw</div>
          <div className="dab-cell-val">
            {data.power_kw != null ? data.power_kw.toFixed(2) : "0.00"}
            <span className="dab-unit"> kW</span>
          </div>
        </div>
        <div className="dab-cell">
          <div className="muted">RPM</div>
          <div className="dab-cell-val">{data.rpm ?? 0}</div>
        </div>
        <div className="dab-cell">
          <div className="muted">Current</div>
          <div className="dab-cell-val">
            {data.current_a != null ? data.current_a.toFixed(1) : "—"}
            <span className="dab-unit"> A</span>
          </div>
        </div>
        <div className="dab-cell">
          <div className="muted">Heatsink</div>
          <div className="dab-cell-val">
            {data.heatsink_f != null ? data.heatsink_f.toFixed(0) : "—"}
            <span className="dab-unit"> °F</span>
          </div>
        </div>
        <div className="dab-cell">
          <div className="muted">Saving</div>
          <div className="dab-cell-val">
            {data.saving_pct != null ? `${data.saving_pct}%` : "—"}
          </div>
        </div>
      </div>

      <table className="dab-totals">
        <tbody>
          <tr>
            <th>Delivered — total</th>
            <td>{fmtGal(data.total_gallons)} gal</td>
            <th>Energy — total</th>
            <td>
              {data.total_energy_kwh != null
                ? `${data.total_energy_kwh.toFixed(1)} kWh` : "—"}
            </td>
          </tr>
          <tr>
            <th>Delivered — period</th>
            <td>{fmtGal(data.period_gallons)} gal</td>
            <th>Energy — period</th>
            <td>
              {data.period_energy_kwh != null
                ? `${data.period_energy_kwh.toFixed(1)} kWh` : "—"}
            </td>
          </tr>
          <tr>
            <th>Runtime</th>
            <td>{data.runtime_hours != null ? `${data.runtime_hours} h` : "—"}</td>
            <th>Starts</th>
            <td>{fmtGal(data.starts)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
