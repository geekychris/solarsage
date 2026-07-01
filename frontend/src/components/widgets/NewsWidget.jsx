import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { api } from "../../api.js";

function prettyDate(s) {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

// One row. Displays the ES title + cached EN if present, plus a manual
// on-demand translate button that also seeds the cache.
function NewsItem({ item, defaultSource, defaultTarget, cachedTranslation, onTranslated }) {
  const [translated, setTranslated] = useState(
    cachedTranslation || item.translated_title || null
  );
  const [showTr, setShowTr] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  // Keep local state in sync when the parent flushes new cached translations.
  useEffect(() => {
    if (cachedTranslation && cachedTranslation !== translated) {
      setTranslated(cachedTranslation);
    }
  }, [cachedTranslation, translated]);

  const doTranslate = useCallback(async (event) => {
    event.preventDefault();
    if (translated) { setShowTr((v) => !v); return; }
    setBusy(true);
    setErr("");
    try {
      // Prefer the news batch endpoint (cheap, cached) if we have an id.
      if (item.id) {
        const r = await api.batchTranslateNews([item.id], defaultSource, defaultTarget);
        const t = r.translated?.[item.id];
        if (t) {
          setTranslated(t);
          setShowTr(true);
          onTranslated?.(item.id, t);
        }
      } else {
        // Fallback for legacy fetches without an id
        const r = await api.translate(item.title, defaultSource, defaultTarget);
        setTranslated(r.target_text);
        setShowTr(true);
      }
    } catch (ex) {
      setErr(ex.message || "translate failed");
    } finally {
      setBusy(false);
    }
  }, [translated, item.id, item.title, defaultSource, defaultTarget, onTranslated]);

  return (
    <div className="news-item">
      <a href={item.link} target="_blank" rel="noreferrer" className="news-title-link">
        <div className="news-title">{item.title}</div>
      </a>
      {translated && showTr && (
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
          title={
            translated
              ? (showTr ? "Hide translation" : "Show cached translation")
              : "Translate to English"
          }
        >
          {busy ? "…" : (translated ? (showTr ? "hide" : "🌐 EN") : "🌐 EN")}
        </button>
      </div>
      {err && <div className="error-inline">{err}</div>}
    </div>
  );
}

export default function NewsWidget({ data }) {
  const [pending, setPending] = useState({}); // id → translated title just fetched
  const requestedRef = useRef(new Set());     // ids we've already asked to translate

  const target = data?.auto_translated_to || "en";
  const source = "es";

  // Collect items that need translation on first render / update.
  const untranslatedIds = useMemo(() => {
    const ids = [];
    for (const f of data?.feeds || []) {
      for (const it of f.items || []) {
        if (it.id && !it.translated_title && !pending[it.id] && !requestedRef.current.has(it.id)) {
          ids.push(it.id);
        }
      }
    }
    return ids;
  }, [data, pending]);

  // Auto-translate what's visible if the widget's config has a target
  // language set (Baja news defaults to "en").
  useEffect(() => {
    if (!data?.auto_translated_to || untranslatedIds.length === 0) return;
    untranslatedIds.forEach((id) => requestedRef.current.add(id));
    let cancelled = false;
    (async () => {
      try {
        const r = await api.batchTranslateNews(untranslatedIds, source, target);
        if (!cancelled && r.translated) {
          setPending((prev) => ({ ...prev, ...r.translated }));
        }
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [data?.auto_translated_to, untranslatedIds, source, target]);

  const noteTranslated = useCallback((id, text) => {
    setPending((prev) => ({ ...prev, [id]: text }));
  }, []);

  if (!data) return <div className="muted">Loading…</div>;
  const feeds = data.feeds || [];
  if (feeds.length === 0) return <div className="muted">No feeds configured.</div>;

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
            <NewsItem
              key={it.id ?? `${i}-${j}`}
              item={it}
              defaultSource={source}
              defaultTarget={target}
              cachedTranslation={pending[it.id]}
              onTranslated={noteTranslated}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
