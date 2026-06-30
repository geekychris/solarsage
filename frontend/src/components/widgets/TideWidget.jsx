import React from "react";

function formatTime(iso, tzOffsetMin) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (tzOffsetMin == null) return d.toLocaleString();
  const local = new Date(d.getTime() + tzOffsetMin * 60_000);
  // Strip the trailing "Z" added by toISOString — we're rendering local time.
  return local.toISOString().replace("T", " ").slice(0, 16);
}

function groupByDate(extremes, tzOffsetMin) {
  const out = new Map();
  for (const e of extremes || []) {
    const d = new Date(e.iso || e.dt * 1000);
    const local = new Date(d.getTime() + (tzOffsetMin || 0) * 60_000);
    const key = local.toISOString().slice(0, 10);
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(e);
  }
  return [...out.entries()].map(([date, items]) => ({ date, items }));
}

export default function TideWidget({ data, tzOffsetMinutes }) {
  if (!data || !data.stations) {
    return <div className="muted">No tide data yet.</div>;
  }
  return (
    <div className="tide-stations">
      {data.stations.map((st) => {
        const days = groupByDate(st.extremes, tzOffsetMinutes);
        return (
          <div key={st.id} className="tide-station">
            <h4 style={{ margin: "4px 0 8px" }}>{st.name}</h4>
            {days.length === 0 && <div className="muted">No extremes returned.</div>}
            <table className="tide-table">
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Date</th>
                  <th style={{ textAlign: "left" }}>Tide</th>
                  <th style={{ textAlign: "left" }}>Local time</th>
                  <th style={{ textAlign: "right" }}>Height (m)</th>
                </tr>
              </thead>
              <tbody>
                {days.flatMap((day) =>
                  day.items.map((e, idx) => (
                    <tr key={`${day.date}-${idx}`}>
                      <td>{idx === 0 ? day.date : ""}</td>
                      <td>
                        <span
                          className={
                            e.type === "High" ? "tide-high" : "tide-low"
                          }
                        >
                          {e.type}
                        </span>
                      </td>
                      <td>{formatTime(e.iso, tzOffsetMinutes).slice(11)}</td>
                      <td style={{ textAlign: "right" }}>
                        {e.height_m?.toFixed?.(2) ?? e.height_m}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
