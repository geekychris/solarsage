import React from "react";

export default function CostcoFuelWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const cs = data.costco_calexico_usd_gal;
  const px = data.pemex_sf_usd_gal_equiv;
  const delta = data.savings_usd_gal_going_north;
  return (
    <div className="fuel">
      <div className="fuel-row">
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Costco Calexico</div>
          <div className="fuel-big">
            {cs != null ? `$${cs.toFixed(2)}/gal` : "—"}
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            source: {data.costco_source}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="muted" style={{ fontSize: 11 }}>Pemex SF (equiv)</div>
          <div className="fuel-big">
            {px != null ? `$${px.toFixed(2)}/gal` : "—"}
          </div>
          {data.pemex_sf_mxn_liter != null && (
            <div className="muted" style={{ fontSize: 11 }}>
              {data.pemex_sf_mxn_liter} MXN/L
            </div>
          )}
        </div>
      </div>
      {delta != null && (
        <div className={`fuel-delta ${delta > 0 ? "positive" : "negative"}`}>
          {delta > 0
            ? `Save $${delta.toFixed(2)}/gal going north`
            : `Costs $${Math.abs(delta).toFixed(2)}/gal more up north`}
        </div>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        {data.note}
      </div>
    </div>
  );
}
