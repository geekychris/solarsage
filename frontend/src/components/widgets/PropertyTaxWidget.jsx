import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function prettyDate(s) {
  if (!s) return "—";
  return new Date(s + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short", month: "long", day: "numeric", year: "numeric",
  });
}

export default function PropertyTaxWidget({ data }) {
  const [busy, setBusy] = useState(false);
  if (!data) return <div className="muted">Loading…</div>;

  const togglePaid = useCallback(async () => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("property_tax");
      const year = new Date().getFullYear();
      const paid_year = cur.config.paid_year === year ? null : year;
      await api.putWidgetConfig("property_tax", { ...cur.config, paid_year });
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <div className="property-tax">
      <div className={`ptax-status ${data.paid_this_year ? "paid" : data.overdue ? "overdue" : "upcoming"}`}>
        {data.paid_this_year
          ? "✓ Paid this year"
          : data.overdue
            ? `⚠ Overdue by ${-data.days_until_due} days`
            : `Due in ${data.days_until_due} days`}
      </div>
      <div style={{ fontSize: 13, marginTop: 4 }}>
        {prettyDate(data.due_this_year)}
      </div>
      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Cadastral: <strong>{data.cadastral_number}</strong>
      </div>
      {data.notes && (
        <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          {data.notes}
        </div>
      )}
      <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
        {data.payment_url && (
          <a
            href={data.payment_url}
            target="_blank"
            rel="noreferrer"
            className="ptax-btn"
          >
            Pay online ↗
          </a>
        )}
        <button onClick={togglePaid} disabled={busy}>
          {busy ? "…" : data.paid_this_year ? "Un-mark paid" : "Mark paid"}
        </button>
      </div>
    </div>
  );
}
