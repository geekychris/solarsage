import React from "react";

function prettyDate(s) {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export default function NewsWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const feeds = data.feeds || [];
  if (feeds.length === 0) {
    return <div className="muted">No feeds configured.</div>;
  }
  return (
    <div className="news">
      {feeds.map((f, i) => (
        <div key={i} className="news-feed">
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            {f.label}
            {f.error && <span className="error-inline"> · {f.error}</span>}
          </div>
          {(f.items || []).map((it, j) => (
            <a
              key={j}
              href={it.link}
              target="_blank"
              rel="noreferrer"
              className="news-item"
            >
              <div className="news-title">{it.title}</div>
              {it.published && (
                <div className="muted" style={{ fontSize: 11 }}>
                  {prettyDate(it.published)}
                </div>
              )}
            </a>
          ))}
        </div>
      ))}
    </div>
  );
}
