import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function prettyDate(s) {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function NewsItem({ item, defaultSource = "es" }) {
  const [translated, setTranslated] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const doTranslate = useCallback(async (event) => {
    event.preventDefault();
    if (translated) { setTranslated(null); return; }
    setBusy(true);
    setErr("");
    try {
      const r = await api.translate(item.title, defaultSource, "en");
      setTranslated(r.target_text);
    } catch (ex) {
      setErr(ex.message || "translate failed");
    } finally {
      setBusy(false);
    }
  }, [translated, item.title, defaultSource]);

  return (
    <div className="news-item">
      <a href={item.link} target="_blank" rel="noreferrer" className="news-title-link">
        <div className="news-title">{item.title}</div>
      </a>
      {translated && (
        <div className="news-translated">🌐 {translated}</div>
      )}
      <div className="news-item-foot">
        {item.published && (
          <span className="muted" style={{ fontSize: 11 }}>
            {prettyDate(item.published)}
          </span>
        )}
        <button
          onClick={doTranslate}
          disabled={busy}
          className="news-translate"
          title={translated ? "Hide translation" : "Translate to English"}
        >
          {busy ? "…" : translated ? "hide" : "🌐 EN"}
        </button>
      </div>
      {err && <div className="error-inline">{err}</div>}
    </div>
  );
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
            {f.parser === "regex_fallback" && (
              <span style={{ marginLeft: 6, color: "#ffd166", fontSize: 10 }}>
                (loose parse)
              </span>
            )}
          </div>
          {(f.items || []).map((it, j) => (
            <NewsItem key={j} item={it} defaultSource="es" />
          ))}
        </div>
      ))}
    </div>
  );
}
