import React, { useEffect, useState } from "react";
import { api } from "../api.js";

function fmtTime(ms, tzOffsetMinutes) {
  if (ms == null) return "—";
  const local = new Date(ms + (tzOffsetMinutes ?? 0) * 60_000);
  // Use UTC accessors on a shifted instant to render the inverter's local clock
  const h = local.getUTCHours().toString().padStart(2, "0");
  const m = local.getUTCMinutes().toString().padStart(2, "0");
  return `${h}:${m}`;
}

function fmtPct(v) {
  if (v == null) return "—";
  return `${v.toFixed(0)}%`;
}

function fmtKwh(v) {
  if (v == null) return "—";
  return `${v.toFixed(1)} kWh`;
}

function fmtTemp(v) {
  if (v == null) return "—";
  return `${Math.round(v)}°F`;
}

function tempColor(t) {
  // Blue (cold) → red (hot), centered around ~75°F
  if (t == null) return "var(--muted)";
  const clamp = Math.max(40, Math.min(110, t));
  const ratio = (clamp - 40) / 70; // 0..1
  const hue = (1 - ratio) * 220; // 220° (blue) → 0° (red)
  return `hsl(${hue.toFixed(0)}, 70%, 55%)`;
}

export default function BatteryCycle({ serial }) {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(7);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    try {
      const r = await api.batteryCycles(serial, days);
      setData(r);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!serial) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial, days]);

  if (err) return <div className="panel"><div className="error">{err}</div></div>;
  if (!data) return null;

  const tz = data.tz_offset_minutes;
  const rows = (data.days || []).slice().reverse(); // newest first

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Daily battery cycle vs temperature</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          capacity {data.battery_capacity_kwh.toFixed(1)} kWh
          {data.soc_field && ` · field ${data.soc_field}`}
        </div>
      </div>
      <div className="toolbar" style={{ marginTop: 10 }}>
        {[3, 7, 14, 30].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={d === days ? "primary" : ""}
            disabled={busy}
          >
            {d}d
          </button>
        ))}
        {busy && <span className="muted">loading…</span>}
      </div>

      {rows.length === 0 ? (
        <div className="empty">No SoC data yet — click <strong>Sync</strong> in the top bar.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="appliance-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Drain started</th>
                <th>Drained to</th>
                <th>Drop</th>
                <th>Energy used</th>
                <th>Charge started</th>
                <th>Fully charged</th>
                <th>Temp (min · avg · max)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const drainDelta =
                  r.drain_start_soc != null && r.min_soc != null
                    ? r.drain_start_soc - r.min_soc
                    : null;
                return (
                  <tr key={r.date}>
                    <td style={{ whiteSpace: "nowrap" }}>{r.date}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {fmtTime(r.drain_start_ts, tz)}
                      <div className="muted" style={{ fontSize: 11 }}>
                        from {fmtPct(r.drain_start_soc)}
                      </div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {fmtTime(r.min_ts, tz)}
                      <div className="muted" style={{ fontSize: 11 }}>
                        to {fmtPct(r.min_soc)}
                      </div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {drainDelta != null ? `${drainDelta.toFixed(0)} pts` : "—"}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{fmtKwh(r.drain_kwh)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {fmtTime(r.charge_start_ts, tz)}
                      <div className="muted" style={{ fontSize: 11 }}>
                        from {fmtPct(r.charge_start_soc)}
                      </div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {fmtTime(r.full_charge_ts, tz)}
                      <div className="muted" style={{ fontSize: 11 }}>
                        peak {fmtPct(r.peak_soc)}
                      </div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <span style={{ color: tempColor(r.temp_min_f) }}>
                        {fmtTemp(r.temp_min_f)}
                      </span>
                      {" · "}
                      <span style={{ color: tempColor(r.temp_avg_f), fontWeight: 600 }}>
                        {fmtTemp(r.temp_avg_f)}
                      </span>
                      {" · "}
                      <span style={{ color: tempColor(r.temp_max_f) }}>
                        {fmtTemp(r.temp_max_f)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        Times in the inverter's local tz. Drain started = last SoC peak before the
        day's low. kWh = drop ÷ 100 × battery capacity.
      </div>
    </div>
  );
}
