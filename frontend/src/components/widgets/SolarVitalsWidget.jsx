import React from "react";

function formatClock(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, {
    hour: "numeric", minute: "2-digit",
  });
}

function StateBadge({ state }) {
  const cls = {
    charging: "sv-charging",
    discharging: "sv-discharging",
    steady: "sv-steady",
  }[state] || "muted";
  const label = {
    charging: "⚡ charging",
    discharging: "🔋 discharging",
    steady: "= steady",
  }[state] || state || "?";
  return <span className={`sv-state ${cls}`}>{label}</span>;
}

export default function SolarVitalsWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const soc = data.soc;
  const pv  = data.pv_kw;
  const load = data.load_kw;
  const net = data.net_kw;
  const p = data.projection;
  const cb = data.cut_back;

  return (
    <div className="sv">
      <div className="sv-top">
        <div className="sv-soc-block">
          <div className="sv-soc-value">{soc != null ? Math.round(soc) : "—"}%</div>
          <div className="sv-soc-bar-outer">
            <div
              className="sv-soc-bar-inner"
              style={{ width: `${Math.max(0, Math.min(100, soc ?? 0))}%` }}
            />
          </div>
          <div className="sv-soc-label">Battery</div>
        </div>
        <div className="sv-flow">
          <div className="sv-flow-line">
            <span className="sv-flow-label">☀ Solar</span>
            <span className="sv-flow-value">
              {pv != null ? pv.toFixed(1) : "—"} kW
            </span>
          </div>
          <div className="sv-flow-line">
            <span className="sv-flow-label">🏠 Load</span>
            <span className="sv-flow-value">
              {load != null ? load.toFixed(1) : "—"} kW
            </span>
          </div>
          <div className="sv-flow-line sv-net">
            <StateBadge state={data.state} />
            {net != null && (
              <span className="sv-flow-value">
                {net > 0 ? "+" : ""}{net.toFixed(2)} kW
              </span>
            )}
          </div>
        </div>
      </div>

      {p && (
        <div className={`sv-projection sv-${p.direction}`}>
          {p.direction === "charging" ? "🔌 Full" : "🪫 Empty"} in{" "}
          <strong>{p.pretty}</strong>
          <span className="muted"> at {formatClock(p.target_at)}</span>
        </div>
      )}
      {cb && (
        <div className="sv-cutback">
          ⚠ Start conserving in <strong>{cb.pretty}</strong>
          <span className="muted"> (~{formatClock(cb.at)}, {cb.target_soc}% left)</span>
        </div>
      )}
      {!p && !cb && (
        <div className="muted" style={{ fontSize: 12 }}>
          System steady — no time projection.
        </div>
      )}
    </div>
  );
}
