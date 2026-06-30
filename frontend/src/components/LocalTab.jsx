import React, { useEffect, useState, useCallback } from "react";
import { api } from "../api.js";
import TideWidget from "./widgets/TideWidget.jsx";
import BorderWidget from "./widgets/BorderWidget.jsx";
import HoaWidget from "./widgets/HoaWidget.jsx";

const RENDERERS = {
  tides: TideWidget,
  border: BorderWidget,
  hoa: HoaWidget,
};

function FetchedAt({ ts, error }) {
  if (error) return <span className="error-inline">error: {error}</span>;
  if (!ts) return <span className="muted">never</span>;
  const d = new Date(ts * 1000);
  return <span className="muted">fetched {d.toLocaleString()}</span>;
}

function WidgetCard({ widget, tzOffsetMinutes, onRefreshed }) {
  const Renderer = RENDERERS[widget.meta.kind];
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      await api.refreshWidget(widget.id);
      onRefreshed();
    } finally {
      setBusy(false);
    }
  }, [widget.id, onRefreshed]);

  return (
    <div className="panel widget-card">
      <div className="widget-head">
        <div>
          <h3 style={{ margin: 0 }}>{widget.meta.name}</h3>
          <div className="muted" style={{ fontSize: 12 }}>
            {widget.meta.description}
          </div>
        </div>
        <div className="widget-head-meta">
          <FetchedAt ts={widget.fetched_at} error={widget.error} />
          <button onClick={refresh} disabled={busy}>
            {busy ? "…" : "Refresh"}
          </button>
        </div>
      </div>
      <div className="widget-body">
        {Renderer ? (
          <Renderer data={widget.data} tzOffsetMinutes={tzOffsetMinutes} />
        ) : (
          <pre style={{ overflow: "auto", maxHeight: 200 }}>
            {JSON.stringify(widget.data, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

export default function LocalTab({ tzOffsetMinutes }) {
  const [widgets, setWidgets] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await api.listWidgets();
      setWidgets(r.widgets || []);
      setErr("");
    } catch (ex) {
      setErr(ex.message || "failed to load widgets");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  if (err) return <div className="error">{err}</div>;
  if (widgets === null) return <div className="muted">Loading widgets…</div>;
  if (widgets.length === 0) {
    return <div className="muted">No widgets registered.</div>;
  }
  return (
    <div className="local-grid">
      {widgets.map((w) => (
        <WidgetCard
          key={w.id}
          widget={w}
          tzOffsetMinutes={tzOffsetMinutes}
          onRefreshed={load}
        />
      ))}
    </div>
  );
}
