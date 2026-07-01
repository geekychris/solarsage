import React from "react";

export default function ConsumptionYoYWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  if (data.note && data.today_kwh_partial == null) {
    return <div className="muted">{data.note}</div>;
  }
  const delta = data.delta_kwh;
  const pct = data.delta_pct;
  const trendClass = delta == null ? "" : delta > 0 ? "yoy-up" : "yoy-down";
  return (
    <div className="yoy">
      <div className="yoy-row">
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Today so far</div>
          <div className="yoy-big">
            {data.today_kwh_partial != null ? `${data.today_kwh_partial} kWh` : "—"}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="muted" style={{ fontSize: 11 }}>Same day last year</div>
          <div className="yoy-big">
            {data.last_year_kwh_partial != null ? `${data.last_year_kwh_partial} kWh` : "—"}
          </div>
        </div>
      </div>
      {delta != null && (
        <div className={`yoy-delta ${trendClass}`}>
          {delta > 0 ? "+" : ""}{delta} kWh
          {pct != null && ` (${pct > 0 ? "+" : ""}${pct}%)`}
        </div>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
        {data.note}
      </div>
    </div>
  );
}
