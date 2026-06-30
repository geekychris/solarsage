import React from "react";

export default function NewsletterWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (!data.latest) {
    return (
      <div className="muted">
        {data.note || "No newsletter PDF found in the HOA scrape."}
      </div>
    );
  }
  return (
    <div>
      <a href={data.latest.url} target="_blank" rel="noreferrer" className="hoa-pdf">
        📰 {data.latest.label}
      </a>
      {data.newsletters && data.newsletters.length > 1 && (
        <details style={{ marginTop: 6 }}>
          <summary className="muted">Older ({data.newsletters.length - 1})</summary>
          <ul style={{ margin: "4px 0 0 16px" }}>
            {data.newsletters.slice(1).map((n, i) => (
              <li key={i}>
                <a href={n.url} target="_blank" rel="noreferrer">{n.label}</a>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
