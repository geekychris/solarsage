import React, { useState, useEffect, useCallback } from "react";
import { api } from "../../api.js";

function speak(text) {
  return api.ttsSay(text);
}

function PhraseCard({ phrase, big }) {
  const [busy, setBusy] = useState(false);
  const doSpeak = async () => {
    setBusy(true);
    try { await speak(phrase.es); } finally { setBusy(false); }
  };
  return (
    <div className={`phrase-card ${big ? "phrase-big" : ""}`}>
      <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
        <span className={big ? "phrase-es-big" : "phrase-es"}>{phrase.es}</span>
        <button onClick={doSpeak} disabled={busy} className="speak-btn" title="Speak">
          {busy ? "…" : "🔊"}
        </button>
      </div>
      <div className="muted phrase-en" style={{ fontSize: big ? 13 : 12 }}>
        {phrase.en}
      </div>
      {phrase.category && (
        <span className="phrase-cat">{phrase.category}</span>
      )}
    </div>
  );
}

export default function SpanishWidget({ data }) {
  const [text, setText] = useState("");
  const [source, setSource] = useState("en");
  const [target, setTarget] = useState("es");
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState([]);
  const [err, setErr] = useState("");

  const loadLog = useCallback(async () => {
    try {
      const r = await api.getTranslations(20);
      setLog(r.translations || []);
    } catch (ex) {
      setErr(ex.message || "translation log failed");
    }
  }, []);

  useEffect(() => { loadLog(); }, [loadLog]);

  const translate = useCallback(async () => {
    if (!text.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await api.translate(text.trim(), source, target);
      setText("");
      loadLog();
    } catch (ex) {
      setErr(ex.message || "translate failed");
    } finally {
      setBusy(false);
    }
  }, [text, source, target, loadLog]);

  const del = async (id) => {
    await api.deleteTranslation(id);
    loadLog();
  };
  const star = async (id) => {
    await api.starTranslation(id);
    loadLog();
  };

  if (!data) return <div className="muted">Loading…</div>;

  return (
    <div className="spanish">
      <div className="muted" style={{ fontSize: 11 }}>Phrase of the day</div>
      <PhraseCard phrase={data.phrase_of_the_day} big />

      <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>Practice set</div>
      <div className="phrase-practice">
        {(data.practice_set || []).map((p, i) => (
          <PhraseCard key={i} phrase={p} />
        ))}
      </div>

      <div style={{ marginTop: 12 }}>
        <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
          Translate anything ({source} → {target})
        </div>
        <div className="translate-input">
          <textarea
            rows={2}
            placeholder={`Text in ${source.toUpperCase()}…`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.ctrlKey && e.key === "Enter" && translate()}
          />
          <div className="translate-controls">
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="en">EN</option>
              <option value="es">ES</option>
            </select>
            <button
              className="translate-swap"
              onClick={() => { const s = source, t = target; setSource(t); setTarget(s); }}
              title="Swap languages"
            >↔</button>
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="es">ES</option>
              <option value="en">EN</option>
            </select>
            <button onClick={translate} disabled={busy || !text.trim()} className="primary">
              {busy ? "…" : "Translate"}
            </button>
          </div>
          {err && <div className="error-inline">{err}</div>}
        </div>
      </div>

      {log.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary className="muted">Your phrase book ({log.length})</summary>
          <div className="translate-log">
            {log.map((t) => (
              <div key={t.id} className={`translate-item ${t.starred ? "starred" : ""}`}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12 }}>
                    <strong>{t.source.toUpperCase()}:</strong> {t.source_text}
                  </div>
                  <div style={{ fontSize: 12 }}>
                    <strong>{t.target.toUpperCase()}:</strong> {t.target_text}
                  </div>
                </div>
                <button onClick={() => speak(t.target_text)} title="Speak translation">🔊</button>
                <button onClick={() => star(t.id)} title="Star">{t.starred ? "★" : "☆"}</button>
                <button onClick={() => del(t.id)} title="Delete">✕</button>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
