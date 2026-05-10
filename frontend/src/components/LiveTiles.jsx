import React from "react";

function Tile({ label, value, unit, sub }) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {sub && <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function fmt(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const v = Number(n);
  return digits === 0 ? Math.round(v).toLocaleString() : v.toFixed(digits);
}

// Try each candidate in order, return {value, source}. Numbers only.
function pick(obj, candidates) {
  if (!obj) return { value: null, source: null };
  for (const k of candidates) {
    const v = obj[k];
    if (typeof v === "number" && !Number.isNaN(v)) {
      return { value: v, source: k };
    }
  }
  return { value: null, source: null };
}

// Sum of fields matching a regex, e.g. ppv1, ppv2, ppv3, ppv4
function sumByPattern(obj, regex) {
  if (!obj) return { value: null, source: null };
  let total = 0;
  const parts = [];
  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === "number" && regex.test(k)) {
      total += v;
      parts.push(k);
    }
  }
  return parts.length ? { value: total, source: parts.join("+") } : { value: null, source: null };
}

function pvPower(r) {
  // Prefer summing per-string powers; many EG4 firmwares only populate ppv1..ppv4
  const strings = sumByPattern(r, /^ppv[1-9]$/);
  if (strings.value != null && strings.value > 0) return strings;
  return pick(r, ["ppv", "pPV", "totalPv", "solarPv", "ppvpCharge"]);
}

export default function LiveTiles({ snapshot }) {
  if (!snapshot) return <div className="tiles" />;
  const r = snapshot.runtime || {};
  const e = snapshot.energy || {};
  const b = snapshot.battery || {};

  const pv = pvPower(r);
  // On EG4 SNA-US firmware, when the house is wired off the EPS / critical
  // loads panel, `consumptionPower` reports 0 and the real draw lives in
  // `peps` (or pEpsL1N + pEpsL2N). Use peps as a fallback so the Load tile
  // isn't permanently zero.
  const cp = pick(r, ["consumptionPower", "pConsumption", "pLoad", "consumption", "totalConsumption"]);
  const epsLegs = sumByPattern(r, /^pEpsL\d+N$/);
  const epsTotal = pick(r, ["peps", "pEps", "pEpsOut", "pEpsTotal"]);
  let load = cp;
  if ((cp.value == null || cp.value === 0) && epsLegs.value && epsLegs.value > 0) {
    load = { value: epsLegs.value, source: epsLegs.source + " (EPS)" };
  } else if ((cp.value == null || cp.value === 0) && epsTotal.value && epsTotal.value > 0) {
    load = { value: epsTotal.value, source: epsTotal.source + " (EPS)" };
  }
  const charge = pick(r, ["pCharge", "ppvpCharge", "batChargePower", "batteryCharging", "pBatChg"]);
  const discharge = pick(r, ["pDisCharge", "batteryDischarging", "batDischargePower", "pBatDchg"]);
  const toGrid = pick(r, ["pToGrid", "gridExport", "pExport"]);
  const fromGrid = pick(r, ["pToUser", "gridImport", "pImport"]);
  const eps = epsTotal;

  const socRuntime = pick(r, ["soc", "batterySoc", "totalSoc"]);
  const socFromUnits =
    b.battery_units && b.battery_units.length > 0
      ? b.battery_units.reduce((s, u) => s + (u.soc || 0), 0) / b.battery_units.length
      : null;
  const soc = socRuntime.value ?? socFromUnits;

  // If load is missing but we have everything else, we can derive it:
  // load = pv + (discharge - charge) + (fromGrid - toGrid)
  let derivedLoad = null;
  if (load.value == null) {
    const components = [pv.value, discharge.value, fromGrid.value]
      .filter((v) => typeof v === "number");
    const negs = [charge.value, toGrid.value].filter((v) => typeof v === "number");
    if (components.length) {
      derivedLoad = components.reduce((s, v) => s + v, 0) - negs.reduce((s, v) => s + v, 0);
    }
  }

  const todayPv = e.todayYieldingText || (e.todayYielding != null ? `${fmt(e.todayYielding, 2)} kWh` : "—");
  const todayLoad = e.todayUsageText || (e.todayUsage != null ? `${fmt(e.todayUsage, 2)} kWh` : "—");
  const todayCharge = e.todayChargingText || (e.todayCharging != null ? `${fmt(e.todayCharging, 2)} kWh` : "—");
  const todayDischarge = e.todayDischargingText || (e.todayDischarging != null ? `${fmt(e.todayDischarging, 2)} kWh` : "—");
  const todayExport = e.todayExportText || (e.todayExport != null ? `${fmt(e.todayExport, 2)} kWh` : "—");
  const todayImport = e.todayImportText || (e.todayImport != null ? `${fmt(e.todayImport, 2)} kWh` : "—");

  return (
    <div className="tiles">
      <Tile label="Status" value={r.statusText || r.status || "—"} />
      <Tile label="Solar PV" value={fmt(pv.value)} unit="W" sub={pv.source} />
      <Tile
        label="Load"
        value={fmt(load.value ?? derivedLoad)}
        unit="W"
        sub={load.source ?? (derivedLoad != null ? "derived" : null)}
      />
      <Tile label="To Grid" value={fmt(toGrid.value)} unit="W" sub={toGrid.source} />
      <Tile label="From Grid" value={fmt(fromGrid.value)} unit="W" sub={fromGrid.source} />
      <Tile label="Battery Charging" value={fmt(charge.value)} unit="W" sub={charge.source} />
      <Tile label="Battery Discharging" value={fmt(discharge.value)} unit="W" sub={discharge.source} />
      <Tile label="EPS / Backup" value={fmt(eps.value)} unit="W" sub={eps.source} />
      <Tile label="Battery SoC" value={soc != null ? fmt(soc, 0) : "—"} unit="%" />
      <Tile label="Battery Voltage" value={b.totalVoltageText || (b.totalVoltage ? `${(b.totalVoltage / 100).toFixed(1)} V` : "—")} />
      <Tile label="Battery Current" value={b.currentText || (b.current != null ? `${b.current} A` : "—")} />
      <Tile label="Today Solar" value={todayPv} />
      <Tile label="Today Load" value={todayLoad} />
      <Tile label="Today Charge" value={todayCharge} />
      <Tile label="Today Discharge" value={todayDischarge} />
      <Tile label="Today Export" value={todayExport} />
      <Tile label="Today Import" value={todayImport} />
    </div>
  );
}
