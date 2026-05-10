import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function HealthPanel({ serial }) {
  const [strings, setStrings] = useState(null);
  const [perf, setPerf] = useState(null);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const [s, p] = await Promise.all([
        api.stringHealth(serial, 14),
        api.performance(serial, 30),
      ]);
      setStrings(s);
      setPerf(p);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (!serial) return;
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial]);

  if (err) return <div className="panel"><div className="error">{err}</div></div>;
  if (!strings && !perf) return null;

  function colorRatio(r) {
    if (r == null) return "#555";
    if (r >= 0.85) return "#3fb950";
    if (r >= 0.6) return "#d29922";
    return "#f85149";
  }

  return (
    <div className="panel">
      <h3 style={{ margin: 0 }}>System health</h3>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Per-string PV balance + actual-vs-expected performance trend.
      </div>

      {/* String health */}
      {strings && strings.strings?.length > 0 && (
        <>
          <h4 style={{ margin: "14px 0 6px", fontSize: 13, color: "var(--muted)" }}>
            String balance ({strings.strings.join(", ")})
          </h4>
          <table className="kv-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th align="left">Day</th>
                {strings.strings.map((s) => <th key={s}>{s}</th>)}
              </tr>
            </thead>
            <tbody>
              {(strings.health || []).slice(-10).map((h) => (
                <tr key={h.date}>
                  <td className="muted">{h.date}</td>
                  {strings.strings.map((s) => {
                    const r = h.ratio_to_strongest[s];
                    return (
                      <td key={s} style={{ color: colorRatio(r) }}>
                        {r == null ? "—" : `${(r * 100).toFixed(0)}%`}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {strings.strings.some((s) => {
            const recent = (strings.health || []).slice(-5);
            const ratios = recent.map((h) => h.ratio_to_strongest[s]).filter((x) => x != null);
            const avg = ratios.reduce((a, b) => a + b, 0) / (ratios.length || 1);
            return avg < 0.3 && ratios.length > 0;
          }) && (
            <div style={{ marginTop: 8, padding: 8, background: "rgba(248, 81, 73, 0.1)", borderRadius: 6, fontSize: 12 }}>
              ⚠️ One or more strings have been producing under 30% of the strongest string consistently.
              This could be a disconnected/unused channel, a panel/cable issue, or shading. Worth investigating.
            </div>
          )}
        </>
      )}

      {/* Performance */}
      {perf?.rows?.length > 0 && (
        <>
          <h4 style={{ margin: "14px 0 6px", fontSize: 13, color: "var(--muted)" }}>
            Daily performance (actual vs irradiance-expected kWh)
          </h4>
          <table className="kv-table" style={{ width: "100%" }}>
            <thead>
              <tr><th align="left">Day</th><th>Actual</th><th>Expected</th><th>Ratio</th></tr>
            </thead>
            <tbody>
              {perf.rows.slice(-10).map((r) => {
                const c = colorRatio(r.ratio);
                return (
                  <tr key={r.date}>
                    <td className="muted">{r.date}</td>
                    <td>{r.actual_kwh.toFixed(1)} kWh</td>
                    <td className="muted">{r.expected_kwh.toFixed(1)} kWh</td>
                    <td style={{ color: c }}>{r.ratio != null ? `${(r.ratio * 100).toFixed(0)}%` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            Ratio under 80% sustained for multiple days suggests soiling, partial shade, or degradation.
            Over 100% means the system is doing better than the simple irradiance model predicts (typical when
            inverter peaks above rated DC).
          </div>
        </>
      )}
    </div>
  );
}
