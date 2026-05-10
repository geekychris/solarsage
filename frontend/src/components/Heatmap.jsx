import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const COLORS = [
  "#1a1f27",  // 0 — no data
  "#173124",
  "#1e4a31",
  "#2a6f44",
  "#3fa55b",
  "#5cd97a",
];

function shade(kwh, max) {
  if (!kwh || max <= 0) return COLORS[0];
  const ratio = Math.min(1, kwh / max);
  const idx = Math.min(COLORS.length - 1, 1 + Math.floor(ratio * (COLORS.length - 2)));
  return COLORS[idx];
}

export default function Heatmap({ serial }) {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(365);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const r = await api.heatmap(serial, days, "ppv");
      setData(r);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    if (!serial) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serial, days]);

  if (err) return <div className="panel"><div className="error">{err}</div></div>;
  if (!data) return null;

  const cells = data.cells || [];
  const max = cells.reduce((m, c) => Math.max(m, c.kwh), 0);

  // Build week-aligned grid: weeks across, days down
  const byDate = new Map(cells.map((c) => [c.date, c]));
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - days);
  // Align to Sunday
  start.setDate(start.getDate() - start.getDay());

  const weeks = [];
  let cur = new Date(start);
  while (cur <= today) {
    const week = [];
    for (let dow = 0; dow < 7; dow++) {
      const key = cur.toISOString().slice(0, 10);
      week.push({ date: key, cell: byDate.get(key) });
      cur.setDate(cur.getDate() + 1);
    }
    weeks.push(week);
  }

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Production heatmap</h3>
        <div className="toolbar">
          {[30, 90, 365].map((d) => (
            <button key={d} className={d === days ? "primary" : ""} onClick={() => setDays(d)}>{d}d</button>
          ))}
        </div>
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Daily kWh produced. Brighter = higher production. {cells.length} days with data, peak {max.toFixed(1)} kWh.
      </div>
      <div style={{ overflowX: "auto", marginTop: 12 }}>
        <div style={{ display: "flex", gap: 3 }}>
          {weeks.map((week, wi) => (
            <div key={wi} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {week.map((d, di) => (
                <div
                  key={di}
                  title={`${d.date}${d.cell ? ` — ${d.cell.kwh.toFixed(1)} kWh` : " — no data"}`}
                  style={{
                    width: 12, height: 12, borderRadius: 2,
                    background: d.cell ? shade(d.cell.kwh, max) : COLORS[0],
                  }}
                />
              ))}
            </div>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, fontSize: 11, color: "var(--muted)" }}>
          <span>less</span>
          {COLORS.map((c, i) => <div key={i} style={{ width: 12, height: 12, background: c, borderRadius: 2 }} />)}
          <span>more</span>
          <span style={{ marginLeft: 12 }}>peak {max.toFixed(1)} kWh</span>
        </div>
      </div>
    </div>
  );
}
