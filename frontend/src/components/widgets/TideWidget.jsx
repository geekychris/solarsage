import React from "react";

function localDateKey(iso, tzOffsetMin) {
  const d = new Date(iso);
  const shifted = new Date(d.getTime() + (tzOffsetMin || 0) * 60_000);
  return shifted.toISOString().slice(0, 10);
}

function formatTimeOfDay(iso, tzOffsetMin) {
  if (!iso) return "—";
  const d = new Date(iso);
  const shifted = new Date(d.getTime() + (tzOffsetMin || 0) * 60_000);
  let h = shifted.getUTCHours();
  const m = shifted.getUTCMinutes();
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return `${h}:${String(m).padStart(2, "0")} ${ampm}`;
}

function todayKey(tzOffsetMin) {
  const now = new Date();
  const shifted = new Date(now.getTime() + (tzOffsetMin || 0) * 60_000);
  return shifted.toISOString().slice(0, 10);
}

function tomorrowKey(tzOffsetMin) {
  const now = new Date();
  const shifted = new Date(now.getTime() + (tzOffsetMin || 0) * 60_000 + 24 * 3_600_000);
  return shifted.toISOString().slice(0, 10);
}

function prettyDate(key) {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function groupByDate(extremes, tzOffsetMin) {
  const out = new Map();
  for (const e of extremes || []) {
    const key = localDateKey(e.iso || e.dt * 1000, tzOffsetMin);
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(e);
  }
  return out;
}

function TideDayCard({ label, dateKey, items, tzOffsetMin, highlight }) {
  return (
    <div className={`tide-day-card ${highlight ? "tide-day-card-hl" : ""}`}>
      <div className="tide-day-head">
        <span className="tide-day-label">{label}</span>
        <span className="muted" style={{ fontSize: 11 }}>
          {dateKey ? prettyDate(dateKey) : ""}
        </span>
      </div>
      {(!items || items.length === 0) && (
        <div className="muted" style={{ fontSize: 12 }}>No tide data.</div>
      )}
      {items && items.length > 0 && (
        <table className="tide-day-table">
          <tbody>
            {items.map((e, idx) => (
              <tr key={idx}>
                <td>
                  <span className={e.type === "High" ? "tide-high" : "tide-low"}>
                    {e.type === "High" ? "▲" : "▼"} {e.type}
                  </span>
                </td>
                <td>{formatTimeOfDay(e.iso, tzOffsetMin)}</td>
                <td style={{ textAlign: "right" }}>
                  {e.height_m?.toFixed?.(2) ?? e.height_m} m
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function TideWidget({ data, tzOffsetMinutes }) {
  if (!data || !data.stations) {
    return <div className="muted">No tide data yet.</div>;
  }
  const today = todayKey(tzOffsetMinutes);
  const tomorrow = tomorrowKey(tzOffsetMinutes);

  return (
    <div className="tide-stations">
      {data.stations.map((st) => {
        const byDay = groupByDate(st.extremes, tzOffsetMinutes);
        const todayItems = byDay.get(today) || [];
        const tomorrowItems = byDay.get(tomorrow) || [];
        const futureKeys = [...byDay.keys()]
          .filter((k) => k !== today && k !== tomorrow && k > today)
          .sort();

        return (
          <div key={st.id} className="tide-station">
            <h4 style={{ margin: "4px 0 8px" }}>{st.name}</h4>

            <div className="tide-day-row">
              <TideDayCard
                label="Today"
                dateKey={today}
                items={todayItems}
                tzOffsetMin={tzOffsetMinutes}
                highlight
              />
              <TideDayCard
                label="Tomorrow"
                dateKey={tomorrow}
                items={tomorrowItems}
                tzOffsetMin={tzOffsetMinutes}
                highlight
              />
            </div>

            {futureKeys.length > 0 && (
              <details className="tide-future" open={false}>
                <summary className="muted">
                  Next {futureKeys.length} day{futureKeys.length === 1 ? "" : "s"}
                </summary>
                <table className="tide-table" style={{ marginTop: 8 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>Date</th>
                      <th style={{ textAlign: "left" }}>Tide</th>
                      <th style={{ textAlign: "left" }}>Time</th>
                      <th style={{ textAlign: "right" }}>Height (m)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {futureKeys.flatMap((k) =>
                      (byDay.get(k) || []).map((e, idx) => (
                        <tr key={`${k}-${idx}`}>
                          <td>{idx === 0 ? prettyDate(k) : ""}</td>
                          <td>
                            <span
                              className={
                                e.type === "High" ? "tide-high" : "tide-low"
                              }
                            >
                              {e.type}
                            </span>
                          </td>
                          <td>{formatTimeOfDay(e.iso, tzOffsetMinutes)}</td>
                          <td style={{ textAlign: "right" }}>
                            {e.height_m?.toFixed?.(2) ?? e.height_m}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </details>
            )}
          </div>
        );
      })}
    </div>
  );
}
