import React from "react";

function Staleness({ meta }) {
  if (!meta) return <span className="muted" style={{ fontSize: 11 }}>no timestamp</span>;
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
  const pxUsd = data.pemex_usd_gal_equiv;
  const pxRegMxn = data.pemex_regular_mxn_l;
  const stations = data.pemex_stations || [];
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

      {/* Real: Pemex nearest */}
      <div className="fuel-source fuel-real">
        <div className="fuel-source-head">
          <span className="fuel-source-name">Pemex — nearest</span>
          <span className="muted fuel-source-tag">CRE gov feed · live</span>
        </div>
        {data.pemex_nearest ? (
          <>
            <div className="fuel-big">
              {pxRegMxn?.toFixed(2)} MXN/L
              {pxUsd != null && (
                <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>
                  ≈ ${pxUsd.toFixed(2)}/gal
                  {data.usd_per_mxn && ` @ ${data.usd_per_mxn.toFixed(4)} MXN/USD`}
                </span>
              )}
            </div>
            <div className="muted" style={{ fontSize: 11 }}>
              {data.pemex_nearest.name.slice(0, 40)} — {data.pemex_nearest.distance_km} km
            </div>
          </>
        ) : (
          <div className="muted">
            {data.pemex_error || "no station found within radius"}
          </div>
        )}
      </div>

      {(data.pemex_locations || []).map((loc) => (
        <details key={loc.name} className="fuel-details" open>
          <summary className="muted" style={{ fontSize: 12, cursor: "pointer", fontWeight: 600 }}>
            {loc.name} — {loc.stations?.length || 0} stations within {loc.radius_km} km
          </summary>
          <table className="fuel-stations">
            <thead>
              <tr>
                <th>Where</th><th>Dist</th><th>Regular</th><th>Premium</th><th>Diesel</th>
              </tr>
            </thead>
            <tbody>
              {(loc.stations || []).map((s) => {
                const addr = s.address || {};
                const where = addr.road || addr.neighbourhood || s.name.slice(0, 28);
                const sub = [addr.neighbourhood, addr.town]
                  .filter(Boolean).join(", ");
                return (
                  <tr key={s.place_id}>
                    <td>
                      <a href={s.maps_url} target="_blank" rel="noreferrer"
                         className="fuel-station-link">
                        {where}
                      </a>
                      {sub && (
                        <div className="muted" style={{ fontSize: 10 }}>{sub}</div>
                      )}
                    </td>
                    <td>{s.distance_km}<span className="muted"> {s.direction}</span></td>
                    <td>{s.regular_mxn_l ?? "—"}</td>
                    <td>{s.premium_mxn_l ?? "—"}</td>
                    <td>{s.diesel_mxn_l  ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      ))}

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
