import React from "react";

function Staleness({ meta }) {
  if (!meta) return <span className="muted">no timestamp</span>;
  const cls = meta.stale ? "fuel-stale" : "muted";
  return (
    <span className={cls} style={{ fontSize: 11 }}>
      {meta.age_days.toFixed(1)}d old{meta.stale ? " — stale" : ""}
    </span>
  );
}

export default function CostcoFuelWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const ca = data.ca_avg_usd_gal;
  const cs = data.costco_calexico_usd_gal;
  const px = data.pemex_sf_usd_gal_equiv;
  const delta = data.savings_usd_gal_going_north;

  return (
    <div className="fuel">
      {/* Real: California retail avg */}
      <div className="fuel-source fuel-real">
        <div className="fuel-source-head">
          <span className="fuel-source-name">CA retail avg</span>
          <span className="muted fuel-source-tag">
            EIA · week of {data.ca_avg_date || "—"}
          </span>
        </div>
        <div className="fuel-big">
          {ca != null ? `$${ca.toFixed(2)}/gal` : "—"}
        </div>
      </div>

      {/* Costco Calexico — manual */}
      <div className="fuel-source">
        <div className="fuel-source-head">
          <span className="fuel-source-name">Costco Calexico</span>
          <Staleness meta={data.costco_staleness} />
        </div>
        <div className="fuel-big">
          {cs != null ? `$${cs.toFixed(2)}/gal` : "—"}
        </div>
      </div>

      {/* Pemex SF — manual */}
      <div className="fuel-source">
        <div className="fuel-source-head">
          <span className="fuel-source-name">Pemex San Felipe</span>
          <Staleness meta={data.pemex_staleness} />
        </div>
        <div className="fuel-big">
          {px != null ? `$${px.toFixed(2)}/gal` : "—"}
          {data.pemex_sf_mxn_liter != null && (
            <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>
              ({data.pemex_sf_mxn_liter} MXN/L
              {data.usd_per_mxn ? ` · ${data.usd_per_mxn.toFixed(4)} MXN/USD` : ""}
              )
            </span>
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
    </div>
  );
}
