import React from "react";

// Palette shared with SmartAcDecisionsWidget so the two feel like siblings.
const MODE_COLOR = {
  ON_TRACK: "#3fb950",
  SURPLUS: "#58a6ff",
  CHARGE_BEHIND: "#d29922",
  DEFICIT: "#f85149",
  EVENING: "#a371f7",
  NIGHT: "#8b97a8",
};

function socColor(soc) {
  if (soc == null) return "#8b97a8";
  if (soc < 20) return "#f85149";
  if (soc < 35) return "#d29922";
  if (soc < 50) return "#c9a642";
  return "#3fb950";
}

// Yellow / orange / red by threshold rank -- matches the iOS view.
function severityColor(belowSoc) {
  if (belowSoc == null) return "#8b97a8";
  if (belowSoc < 20) return "#f85149";
  if (belowSoc < 35) return "#d29922";
  return "#e8c547";
}

function keepMaxLabel(km) {
  if (km == null) return "monitor";
  if (km === 0) return "all off";
  return `keep ${km}`;
}

function keepMaxColor(km) {
  if (km == null) return "#8b97a8";
  if (km === 0) return "#f85149";
  return "#d29922";
}

function TierRow({ step, isActive, soc }) {
  const bg = isActive ? "rgba(214, 149, 34, 0.15)" : "transparent";
  const border = isActive ? "1px solid #d29922" : "1px solid rgba(255,255,255,0.05)";
  return (
    <div
      style={{
        display: "flex", alignItems: "flex-start", gap: 10,
        padding: "8px 10px", borderRadius: 6,
        background: bg, border, marginBottom: 4,
      }}
    >
      <div
        style={{
          width: 10, height: 10, borderRadius: "50%",
          background: severityColor(step.below_soc),
          marginTop: 6, flexShrink: 0,
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <div style={{ fontWeight: isActive ? 700 : 600, fontSize: 13 }}>
            Below {Math.round(step.below_soc)}%
          </div>
          <div style={{
            color: keepMaxColor(step.keep_max),
            fontWeight: 600, fontSize: 11,
          }}>
            {keepMaxLabel(step.keep_max)}
          </div>
        </div>
        <div style={{ fontSize: 11, color: "#8b97a8", marginTop: 2 }}>
          {step.note}
        </div>
        {isActive && soc != null && (
          <div style={{ fontSize: 11, color: "#d29922", marginTop: 2, fontWeight: 600 }}>
            Active · SoC {Math.round(soc)}%
          </div>
        )}
      </div>
    </div>
  );
}

function SafetyStatus({ safety, soc }) {
  if (!safety || !(safety.schedule || []).length) {
    return (
      <div style={{ fontSize: 12, color: "#8b97a8" }}>
        No soc_shed_schedule configured on the scheduler.
      </div>
    );
  }
  const active = safety.active_step;
  const next = safety.next_action;
  if (active) {
    return (
      <div style={{
        padding: "8px 10px", background: "rgba(248,81,73,0.10)",
        border: "1px solid #f85149", borderRadius: 6,
      }}>
        <div style={{ fontWeight: 700, color: "#f85149" }}>
          ⚠ Active: below {Math.round(active.below_soc)}%
        </div>
        <div style={{ fontSize: 12, color: "#c9d1d9", marginTop: 2 }}>
          {active.note}
        </div>
        {safety.recovery_at != null && (
          <div style={{ fontSize: 12, color: "#58a6ff", marginTop: 4 }}>
            Releases when SoC ≥ {safety.recovery_at}%
          </div>
        )}
      </div>
    );
  }
  return (
    <div style={{
      padding: "8px 10px", background: "rgba(63,185,80,0.08)",
      border: "1px solid #3fb950", borderRadius: 6,
    }}>
      <div style={{ fontWeight: 700, color: "#3fb950" }}>
        ✓ No shed active
      </div>
      {next && (
        <div style={{ fontSize: 12, color: "#c9d1d9", marginTop: 4 }}>
          Next tier at SoC {Math.round(next.below_soc)}%
          {typeof next.delta_soc === "number" && next.delta_soc > 0 && (
            <span> · {Math.round(next.delta_soc)}% headroom</span>
          )}
        </div>
      )}
    </div>
  );
}

export default function SmartAcPlanWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;

  const modeColor = MODE_COLOR[data.mode] || "#c9d1d9";
  const soc = data.soc;
  const target = data.target_on || [];
  const safety = data.safety || {};
  const schedule = (safety.schedule || []).slice().sort(
    (a, b) => (b.below_soc || 0) - (a.below_soc || 0), // descending: gentlest first
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Intent sentence -- the human-readable "what am I doing" line */}
      {data.intent_summary && (
        <div style={{
          fontSize: 13, lineHeight: 1.4,
          padding: "8px 10px", background: "rgba(88,166,255,0.08)",
          border: "1px solid rgba(88,166,255,0.3)", borderRadius: 6,
        }}>
          {data.intent_summary}
        </div>
      )}

      {/* Snapshot: mode / SoC / occupied / enabled */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 12 }}>
        <div>
          <span style={{ color: "#8b97a8" }}>Mode: </span>
          <span style={{ color: modeColor, fontWeight: 700 }}>{data.mode || "—"}</span>
        </div>
        <div>
          <span style={{ color: "#8b97a8" }}>SoC: </span>
          <span style={{ color: socColor(soc), fontWeight: 700 }}>
            {soc != null ? `${Math.round(soc)}%` : "—"}
          </span>
        </div>
        <div>
          <span style={{ color: "#8b97a8" }}>Occupancy: </span>
          {data.unoccupied === true ? "Unoccupied" :
           data.unoccupied === false ? "Occupied" : "—"}
        </div>
        <div>
          <span style={{ color: "#8b97a8" }}>Enabled: </span>
          <span style={{ color: data.enabled ? "#3fb950" : "#d29922", fontWeight: 600 }}>
            {data.enabled ? "Yes" : "Preview only"}
          </span>
        </div>
      </div>

      {/* Running rooms */}
      <div style={{ fontSize: 12 }}>
        <span style={{ color: "#8b97a8" }}>Running: </span>
        {target.length > 0 ? (
          <span style={{ color: "#3fb950", fontWeight: 600 }}>
            {target.join(", ")}
          </span>
        ) : (
          <span style={{ color: "#8b97a8" }}>(none)</span>
        )}
      </div>

      {/* Safety status card */}
      <div>
        <div style={{ fontSize: 11, color: "#8b97a8", marginBottom: 4 }}>
          SAFETY STATUS
        </div>
        <SafetyStatus safety={safety} soc={soc} />
      </div>

      {/* All tiers, gentlest → most restrictive */}
      {schedule.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: "#8b97a8", marginBottom: 4 }}>
            ALL TIERS
          </div>
          {schedule.map((step, i) => (
            <TierRow
              key={step.below_soc ?? i}
              step={step}
              isActive={
                safety.active_step != null &&
                safety.active_step.below_soc === step.below_soc
              }
              soc={soc}
            />
          ))}
        </div>
      )}
    </div>
  );
}
