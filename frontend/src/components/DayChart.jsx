import React, { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api.js";

const SERIES_STYLE = {
  ppv: { name: "Solar PV (W)", color: "#2ea043", width: 3 },
  consumptionPower: { name: "Load (W)", color: "#f85149", width: 2 },
  pCharge: { name: "Battery Charging (W)", color: "#58a6ff", width: 2 },
  pDisCharge: { name: "Battery Discharging (W)", color: "#a371f7", width: 2 },
  gridPower: { name: "Grid (W)", color: "#d29922", width: 2 },
  soc: { name: "SoC (%)", color: "#79c0ff", width: 2, yAxis: "right" },
  acCouplePower: { name: "AC Coupled (W)", color: "#ff9d76", width: 2 },
};

function fmtTime(ts, tzOffsetMinutes) {
  const d = new Date(ts);
  const local = new Date(d.getTime() + (tzOffsetMinutes + d.getTimezoneOffset()) * 60_000);
  return local.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtDate(d) {
  return d.toISOString().slice(0, 10);
}

function addDays(dateStr, n) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + n);
  return fmtDate(dt);
}

export default function DayChart({ serial, todayLocal }) {
  const [date, setDate] = useState(todayLocal);
  const [data, setData] = useState(null);
  const [coverage, setCoverage] = useState({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [backfillBusy, setBackfillBusy] = useState(false);
  const [backfillMsg, setBackfillMsg] = useState("");

  async function loadCoverage() {
    try {
      const r = await api.coverage(serial);
      setCoverage(r.by_date || {});
    } catch (ex) {
      // non-fatal
    }
  }

  async function load(dateToLoad) {
    setBusy(true);
    setErr("");
    try {
      const r = await api.dayChart(serial, dateToLoad);
      setData(r);
    } catch (ex) {
      setErr(ex.message);
      setData(null);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!serial) return;
    loadCoverage();
    load(date);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial, date]);

  async function runBackfill(days) {
    setBackfillBusy(true);
    setBackfillMsg("");
    try {
      const r = await api.backfill(serial, days);
      const ok = r.days.filter((d) => d.ok).length;
      const failed = r.days.length - ok;
      setBackfillMsg(
        `Pulled ${r.total_values_written.toLocaleString()} values across ${ok} day${ok === 1 ? "" : "s"}` +
          (failed ? ` (${failed} failed)` : "")
      );
      await loadCoverage();
      await load(date);
    } catch (ex) {
      setBackfillMsg(`Backfill failed: ${ex.message}`);
    } finally {
      setBackfillBusy(false);
    }
  }

  const rows = useMemo(() => {
    if (!data) return [];
    // Build a unified time-indexed row set
    const byTs = new Map();
    for (const [field, points] of Object.entries(data.series || {})) {
      for (const p of points) {
        const r = byTs.get(p.ts) || { ts: p.ts };
        r[field] = p.value;
        byTs.set(p.ts, r);
      }
    }
    const sorted = [...byTs.values()].sort((a, b) => a.ts - b.ts);
    const tz = data.tz_offset_minutes;
    return sorted.map((r) => ({ ...r, label: fmtTime(r.ts, tz) }));
  }, [data]);

  const availableFields = Object.keys(data?.series || {});
  const dates = Object.keys(coverage).sort();
  const isToday = date === todayLocal;

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Day view</h3>
        <div className="muted" style={{ fontSize: 12 }}>
          {data && `${rows.length} points · ${availableFields.length} channels`}
        </div>
      </div>

      <div className="toolbar" style={{ marginTop: 10 }}>
        <button onClick={() => setDate(addDays(date, -1))} disabled={busy}>← Prev</button>
        <input
          type="date"
          value={date}
          max={todayLocal}
          onChange={(e) => setDate(e.target.value)}
        />
        <button onClick={() => setDate(addDays(date, 1))} disabled={busy || isToday}>Next →</button>
        <button onClick={() => setDate(todayLocal)} disabled={busy || isToday}>Today</button>
        {dates.length > 0 && (
          <select
            value={dates.includes(date) ? date : ""}
            onChange={(e) => e.target.value && setDate(e.target.value)}
            title="Days with stored history"
          >
            <option value="">— stored days —</option>
            {dates.slice().reverse().map((d) => (
              <option key={d} value={d}>{d} ({coverage[d]})</option>
            ))}
          </select>
        )}
        <span style={{ flex: 1 }} />
        <label>Backfill</label>
        <button onClick={() => runBackfill(7)} disabled={backfillBusy}>7d</button>
        <button onClick={() => runBackfill(30)} disabled={backfillBusy}>30d</button>
        <button onClick={() => runBackfill(90)} disabled={backfillBusy}>90d</button>
        {backfillBusy && <span className="muted">pulling…</span>}
      </div>

      {backfillMsg && <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{backfillMsg}</div>}
      {err && <div className="error" style={{ marginTop: 8 }}>{err}</div>}

      {data && rows.length === 0 ? (
        <div className="empty">
          No data for {date}. Use the Backfill buttons above to pull historical days from EG4.
        </div>
      ) : null}

      {rows.length > 0 && (
        <div style={{ width: "100%", height: 360, marginTop: 12 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 10, right: 50, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#232a35" strokeDasharray="3 3" />
              <XAxis
                dataKey="label"
                stroke="#8b97a8"
                tick={{ fill: "#8b97a8", fontSize: 11 }}
                minTickGap={40}
              />
              <YAxis
                yAxisId="left"
                stroke="#8b97a8"
                tick={{ fill: "#8b97a8", fontSize: 11 }}
                label={{ value: "Watts", angle: -90, position: "insideLeft", fill: "#8b97a8", fontSize: 11 }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                stroke="#8b97a8"
                domain={[0, 100]}
                tick={{ fill: "#8b97a8", fontSize: 11 }}
                label={{ value: "SoC %", angle: 90, position: "insideRight", fill: "#8b97a8", fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: "#151a22", border: "1px solid #232a35" }}
                labelStyle={{ color: "#8b97a8" }}
              />
              <Legend wrapperStyle={{ color: "#8b97a8", fontSize: 12 }} />
              <ReferenceLine y={0} yAxisId="left" stroke="#444" />
              {availableFields.map((f) => {
                const cfg = SERIES_STYLE[f] || { name: f, color: "#999", width: 1 };
                return (
                  <Line
                    key={f}
                    yAxisId={cfg.yAxis === "right" ? "right" : "left"}
                    type="monotone"
                    dataKey={f}
                    name={cfg.name}
                    stroke={cfg.color}
                    strokeWidth={cfg.width}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
