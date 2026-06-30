import React from "react";

function groupBy(items, key) {
  const m = new Map();
  for (const it of items) {
    const k = it[key] || "Other";
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(it);
  }
  return m;
}

export default function QuickLinksWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const links = data.links || [];
  if (links.length === 0) {
    return (
      <div className="muted">
        No links configured — add some via Settings.
      </div>
    );
  }
  const groups = groupBy(links, "group");
  return (
    <div className="quicklinks">
      {[...groups.entries()].map(([group, items]) => (
        <div key={group} className="ql-group">
          <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>
            {group}
          </div>
          {items.map((l, i) => (
            <a
              key={`${l.url}-${i}`}
              href={l.url}
              target="_blank"
              rel="noreferrer"
              className="ql-link"
            >
              {l.label}
            </a>
          ))}
        </div>
      ))}
    </div>
  );
}
