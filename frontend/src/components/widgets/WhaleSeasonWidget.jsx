import React from "react";

export default function WhaleSeasonWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className={`whale ${data.in_season ? "whale-open" : "whale-closed"}`}>
      <div className="whale-big">
        {data.in_season ? "🐋 In season" : "Off season"}
      </div>
      <div style={{ fontSize: 13, marginTop: 4 }}>
        {data.in_season
          ? `Season ends in ${data.days_until_end} days (${data.ends_at})`
          : `Season starts in ${data.days_until_start} days (${data.starts_at})`}
      </div>
      <details style={{ marginTop: 8 }}>
        <summary className="muted" style={{ fontSize: 12 }}>
          Common species
        </summary>
        <ul style={{ margin: "6px 0 0 16px", fontSize: 12 }}>
          {(data.species || []).map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      </details>
    </div>
  );
}
