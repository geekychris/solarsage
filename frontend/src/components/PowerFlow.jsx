import React from "react";

// Animated power-flow diagram. Reads the same `snapshot` Dashboard already
// polls every 15s — refreshes automatically, no extra fetches.
//
// Sources (into inverter): solar strings, battery discharge, grid import
// Sinks (out of inverter):  battery charge, grid export, EPS panel, main panel
//
// Per-string solar shows when the inverter reports ppv1..ppvN; otherwise we
// fall back to the aggregate ppv. The grid node hides automatically on
// off-grid installs (detected via `fac` and `vacr` both being absent/zero).
// EG4 does NOT report per-house-circuit load — that needs an external CT
// monitor.

const COLOR = {
  solar:     "#2ea043",
  charge:    "#58a6ff",
  discharge: "#a371f7",
  export:    "#d29922",
  import:    "#9b6dff",
  load:      "#f85149",
  eps:       "#ff9d76",
  idle:      "#2a3140",
  node:      "#151a22",
  text:      "#e6e9ef",
  muted:     "#8b97a8",
};

function pickNum(o, keys) {
  for (const k of keys) {
    const v = o?.[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

function sumByPattern(o, re) {
  const parts = [];
  let sum = 0;
  for (const [k, v] of Object.entries(o || {})) {
    if (typeof v === "number" && Number.isFinite(v) && re.test(k)) {
      parts.push({ key: k, value: v });
      sum += v;
    }
  }
  parts.sort((a, b) => a.key.localeCompare(b.key));
  return { sum, parts };
}

function flowSpeed(watts) {
  const w = Math.abs(watts);
  if (w < 20) return 0;
  return Math.max(0.4, 3 / Math.log10(w + 10));
}

function fmtW(v) {
  if (v == null) return "—";
  const n = Math.round(v);
  if (Math.abs(n) >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return `${n}`;
}

// 20×20 icons drawn at the origin; the caller translates them into position.
function Icon({ name, color }) {
  const s = { stroke: color, strokeWidth: 1.4, fill: "none", strokeLinejoin: "round", strokeLinecap: "round" };
  switch (name) {
    case "solar":
      return (
        <g>
          <rect x="1" y="3" width="18" height="13" rx="1" {...s} />
          <line x1="1"  y1="9.5" x2="19" y2="9.5" {...s} />
          <line x1="7"  y1="3"   x2="7"  y2="16"  {...s} />
          <line x1="13" y1="3"   x2="13" y2="16"  {...s} />
        </g>
      );
    case "battery":
      return (
        <g>
          <rect x="1" y="5" width="16" height="10" rx="1.5" {...s} />
          <rect x="17" y="8" width="2" height="4" fill={color} stroke="none" />
          <rect x="3" y="7" width="5" height="6" fill={color} stroke="none" />
        </g>
      );
    case "grid":
      return (
        <g>
          <line x1="10" y1="2"  x2="2"  y2="17" {...s} />
          <line x1="10" y1="2"  x2="18" y2="17" {...s} />
          <line x1="5"  y1="12" x2="15" y2="12" {...s} />
          <line x1="6.5" y1="8" x2="13.5" y2="8" {...s} />
        </g>
      );
    case "house":
      return (
        <g>
          <path d="M2 10 L10 2 L18 10 V17 H2 Z" {...s} />
          <rect x="8" y="11" width="4" height="6" {...s} />
        </g>
      );
    case "eps":
      return (
        <g>
          <path d="M10 1 L2 4 V11 C2 14 5.5 16.5 10 18 C14.5 16.5 18 14 18 11 V4 Z" {...s} />
          <path d="M6.5 9.5 L9 12 L14 7" {...s} />
        </g>
      );
    case "inverter":
      return (
        <g>
          <path d="M11 1 L4 11 H9 L8 18 L15 8 H10 Z" fill={color} stroke={color} strokeWidth="0.5" />
        </g>
      );
    default:
      return null;
  }
}

function FlowLine({ ax, ay, bx, by, value, color, reverse = false }) {
  const speed = flowSpeed(value);
  const [x1, y1, x2, y2] = reverse ? [bx, by, ax, ay] : [ax, ay, bx, by];
  return (
    <>
      <line x1={ax} y1={ay} x2={bx} y2={by} stroke={COLOR.idle} strokeWidth={2.5} />
      {speed > 0 && (
        <line
          x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={color}
          strokeWidth={2.5}
          strokeDasharray="8 5"
          strokeLinecap="round"
          style={{ animation: `solarsage-flow ${speed}s linear infinite` }}
        />
      )}
    </>
  );
}

function Node({ x, y, w, h, label, value, unit = "W", sub, color, icon, soc }) {
  const cx = x + w / 2;
  const iconSize = 18;
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={8} fill={COLOR.node} stroke={color} strokeWidth={1.3} />
      <g transform={`translate(${cx - iconSize / 2}, ${y + 6})`}>
        <Icon name={icon} color={color} />
      </g>
      <text x={cx} y={y + 42} textAnchor="middle" fill={COLOR.text} fontSize={15} fontWeight={700}>
        {fmtW(value)}
        <tspan fill={COLOR.muted} fontSize={9} dx={2}>{unit}</tspan>
      </text>
      {sub && (
        <text x={cx} y={y + 55} textAnchor="middle" fill={COLOR.muted} fontSize={9}>
          {sub}
        </text>
      )}
      {label && (
        <text x={cx} y={y + h + 11} textAnchor="middle" fill={color} fontSize={10} fontWeight={600}>
          {label}
        </text>
      )}
      {soc != null && (
        <>
          <rect x={x + 8} y={y + h - 8} width={w - 16} height={4} rx={2} fill="#0e1116" stroke={COLOR.muted} strokeOpacity={0.3} />
          <rect x={x + 8} y={y + h - 8} width={(w - 16) * Math.max(0, Math.min(100, soc)) / 100} height={4} rx={2} fill={color} />
          <text x={cx} y={y + h - 11} textAnchor="middle" fill={COLOR.muted} fontSize={9}>
            {Math.round(soc)}%
          </text>
        </>
      )}
    </g>
  );
}

export default function PowerFlow({ snapshot }) {
  if (!snapshot) {
    return (
      <div className="panel">
        <h3 style={{ margin: 0 }}>Power flow</h3>
        <div className="empty">Waiting for live data…</div>
      </div>
    );
  }
  const r = snapshot.runtime || {};
  const b = snapshot.battery || {};

  const pvStrings = sumByPattern(r, /^ppv[1-9]$/);
  const pvAgg = pickNum(r, ["ppv", "pPV", "totalPv", "solarPv", "ppvpCharge"]);
  const totalPv = pvStrings.parts.length ? pvStrings.sum : (pvAgg ?? 0);
  const strings = pvStrings.parts.length ? pvStrings.parts : (totalPv ? [{ key: "ppv", value: totalPv }] : []);

  const charge = pickNum(r, ["pCharge", "batChargePower", "pBatChg", "batteryCharging"]) || 0;
  const discharge = pickNum(r, ["pDisCharge", "batDischargePower", "pBatDchg", "batteryDischarging"]) || 0;
  const toGrid = pickNum(r, ["pToGrid", "gridExport", "pExport"]) || 0;
  const fromGrid = pickNum(r, ["pToUser", "gridImport", "pImport"]) || 0;
  const epsLegs = sumByPattern(r, /^pEpsL\d+N$/).sum;
  const eps = epsLegs || pickNum(r, ["peps", "pEps", "pEpsOut", "pEpsTotal"]) || 0;
  const mainLoad = pickNum(r, ["consumptionPower", "pConsumption", "pLoad"]) || 0;

  // Grid presence: utility frequency or voltage > 0 means a live grid is wired in.
  // Pure off-grid systems read 0 (or omit the field), in which case hide the grid node.
  const gridFreq = pickNum(r, ["fac", "gridFreq", "frequency"]) || 0;
  const gridVoltage = pickNum(r, ["vacr", "vac", "vacs", "vact", "gridVoltage"]) || 0;
  const hasGrid = gridFreq > 1 || gridVoltage > 1 || toGrid > 0 || fromGrid > 0;

  const socRuntime = pickNum(r, ["soc", "batterySoc", "totalSoc"]);
  const socFromUnits = b.battery_units?.length
    ? b.battery_units.reduce((s, u) => s + (u.soc || 0), 0) / b.battery_units.length
    : null;
  const soc = socRuntime ?? socFromUnits;

  // -- layout (viewBox 0 0 560 360) --
  const W = 560, H = 360;
  const invX = 240, invY = 145, invW = 80, invH = 60;
  const invTop   = { x: invX + invW / 2, y: invY };
  const invLeft  = { x: invX, y: invY + invH / 2 };
  const invRight = { x: invX + invW, y: invY + invH / 2 };
  const invBLeft = { x: invX + 18, y: invY + invH };
  const invBRight= { x: invX + invW - 18, y: invY + invH };

  const N = Math.max(1, strings.length);
  const stringBoxW = N === 1 ? 90 : N === 2 ? 88 : N === 3 ? 80 : 70;
  const stringBoxH = 60;
  const stringY = 18;
  const stringGap = 16;
  const totalRowW = N * stringBoxW + (N - 1) * stringGap;
  const stringX0 = (W - totalRowW) / 2;

  const charging = charge > 20;
  const discharging = discharge > 20;
  const exporting = toGrid > 20;
  const importing = fromGrid > 20;

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>Power flow</h3>
        <div className="muted" style={{ fontSize: 11 }}>
          live · refreshes with snapshot poll
        </div>
      </div>
      <style>{`@keyframes solarsage-flow { to { stroke-dashoffset: -13; } }`}</style>
      <div style={{ width: "100%", maxWidth: 720, margin: "12px auto 0" }}>
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Power flow diagram">
          {/* Solar strings → inverter top */}
          {strings.map((s, i) => {
            const sx = stringX0 + i * (stringBoxW + stringGap);
            const cx = sx + stringBoxW / 2;
            const by = stringY + stringBoxH;
            return (
              <g key={s.key}>
                <FlowLine ax={cx} ay={by} bx={invTop.x} by={invTop.y} value={s.value} color={COLOR.solar} />
                <Node
                  x={sx} y={stringY} w={stringBoxW} h={stringBoxH}
                  label={N === 1 ? "Solar PV" : `Solar ${s.key.replace("ppv", "")}`}
                  value={s.value}
                  color={COLOR.solar}
                  icon="solar"
                />
              </g>
            );
          })}

          {/* Battery ↔ Inverter */}
          <FlowLine
            ax={100} ay={invLeft.y}
            bx={invLeft.x} by={invLeft.y}
            value={charging ? charge : discharge}
            color={charging ? COLOR.charge : COLOR.discharge}
            reverse={charging}
          />
          <Node
            x={10} y={138} w={90} h={70}
            label="Battery"
            value={charging ? charge : discharging ? discharge : 0}
            sub={charging ? "charging" : discharging ? "discharging" : "idle"}
            color={charging ? COLOR.charge : discharging ? COLOR.discharge : COLOR.muted}
            icon="battery"
            soc={soc}
          />

          {/* Grid ↔ Inverter — hidden on off-grid installs */}
          {hasGrid && (
            <>
              <FlowLine
                ax={invRight.x} ay={invRight.y}
                bx={460} by={invRight.y}
                value={exporting ? toGrid : fromGrid}
                color={exporting ? COLOR.export : COLOR.import}
                reverse={importing}
              />
              <Node
                x={460} y={148} w={90} h={55}
                label="Grid"
                value={exporting ? toGrid : importing ? fromGrid : 0}
                sub={exporting ? "exporting" : importing ? "importing" : "idle"}
                color={exporting ? COLOR.export : importing ? COLOR.import : COLOR.muted}
                icon="grid"
              />
            </>
          )}

          {/* Inverter bottom-left → EPS */}
          <FlowLine
            ax={invBLeft.x} ay={invBLeft.y}
            bx={195} by={275}
            value={eps}
            color={COLOR.eps}
          />
          <Node
            x={140} y={275} w={110} h={55}
            label="Critical loads (EPS)"
            value={eps}
            sub={epsLegs ? "L1+L2" : eps > 20 ? "drawing" : "idle"}
            color={eps > 20 ? COLOR.eps : COLOR.muted}
            icon="eps"
          />

          {/* Inverter bottom-right → main panel */}
          <FlowLine
            ax={invBRight.x} ay={invBRight.y}
            bx={365} by={275}
            value={mainLoad}
            color={COLOR.load}
          />
          <Node
            x={310} y={275} w={110} h={55}
            label="Main panel"
            value={mainLoad}
            sub={mainLoad > 20 ? "drawing" : "idle"}
            color={mainLoad > 20 ? COLOR.load : COLOR.muted}
            icon="house"
          />

          {/* Inverter at center */}
          <rect x={invX} y={invY} width={invW} height={invH} rx={10} fill={COLOR.node} stroke={COLOR.muted} strokeWidth={1.3} />
          <g transform={`translate(${invTop.x - 9}, ${invY + 5})`}>
            <Icon name="inverter" color={COLOR.muted} />
          </g>
          <text x={invTop.x} y={invY + 42} textAnchor="middle" fill={COLOR.text} fontSize={13} fontWeight={700}>
            {fmtW(totalPv)}<tspan fill={COLOR.muted} fontSize={9} dx={2}>W</tspan>
          </text>
          <text x={invTop.x} y={invY + invH + 11} textAnchor="middle" fill={COLOR.muted} fontSize={10} fontWeight={600}>
            INVERTER
          </text>
        </svg>
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
        Animation speed scales with power. Critical loads (EPS) and Main panel are the inverter's two AC outputs — the
        EG4 doesn't report per-circuit splits, that would need an external CT monitor.
      </div>
    </div>
  );
}
