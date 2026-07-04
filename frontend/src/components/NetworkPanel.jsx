import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return `${m}m ${String(rs).padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return `${h}h ${String(rm).padStart(2, "0")}m`;
}

function fmtWhen(ts) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString();
}

function targetLabel(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export default function NetworkPanel() {
  const [status, setStatus] = useState(null);
  const [outages, setOutages] = useState([]);
  const [history, setHistory] = useState([]);
  const [err, setErr] = useState("");

  async function load() {
    try {
      const [s, o, h] = await Promise.all([
        api.networkStatus(),
        api.networkOutages(20),
        api.networkHistory(24),
      ]);
      setStatus(s);
      setOutages(o.outages || []);
      setHistory(h.checks || []);
      setErr("");
    } catch (ex) {
      setErr(ex.message);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  // Bucket checks into 5-minute cells for a simple timeline strip.
  const cells = useMemo(() => {
    if (!status) return [];
    const bucketMs = 5 * 60_000;
    const nowMs = status.now_ms;
    const start = nowMs - 24 * 3_600_000;
    const numCells = Math.ceil((nowMs - start) / bucketMs);
    const grid = new Array(numCells).fill(null).map(() => ({ total: 0, ok: 0 }));
    for (const c of history) {
      const idx = Math.floor((c.ts - start) / bucketMs);
      if (idx < 0 || idx >= numCells) continue;
      grid[idx].total += 1;
      if (c.ok) grid[idx].ok += 1;
    }
    return grid.map((g, i) => {
      const ts = start + i * bucketMs;
      let state = "gap";
      if (g.total > 0) {
        if (g.ok === g.total) state = "up";
        else if (g.ok === 0) state = "down";
        else state = "partial";
      }
      return { ts, ...g, state };
    });
  }, [history, status]);

  if (err && !status) {
    return <div className="panel"><div className="error">{err}</div></div>;
  }
  if (!status) return null;

  const isDown = !!status.open_outage;
  const latestOk = status.latest?.any_ok;
  const stateColor = isDown ? "#f85149" : (latestOk ? "#3fb950" : "#d29922");
  const stateLabel = isDown
    ? "Offline"
    : latestOk ? "Online" : (status.latest ? "Degraded" : "Unknown");
  const openStartedMs = status.open_outage?.started_ts;
  const openDurationS = openStartedMs
    ? (status.now_ms - openStartedMs) / 1000
    : null;

  const cellColor = {
    up: "#3fb950",
    down: "#f85149",
    partial: "#d29922",
    gap: "#2a2f36",
  };

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>Network connectivity</h3>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          checks every ~60s
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10 }}>
        <span
          aria-label={stateLabel}
          style={{
            width: 12, height: 12, borderRadius: "50%",
            background: stateColor, display: "inline-block",
            boxShadow: `0 0 8px ${stateColor}`,
          }}
        />
        <div style={{ fontSize: 16, fontWeight: 600 }}>{stateLabel}</div>
        <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>
          last check {fmtWhen(status.latest?.ts)}
        </div>
      </div>

      {isDown && (
        <div className="alert-row" style={{ borderLeft: "3px solid #f85149", marginTop: 10 }}>
          <div className="alert-text">
            Network unreachable for <b>{fmtDuration(openDurationS)}</b>
            {" · "}since {fmtWhen(openStartedMs)}
          </div>
          <div className="alert-rule muted">
            (Telegram will fire when connectivity recovers.)
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 24, marginTop: 12, flexWrap: "wrap" }}>
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Uptime (24h)</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>
            {status.uptime_pct_24h == null ? "—" : `${status.uptime_pct_24h.toFixed(2)}%`}
          </div>
        </div>
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Avg latency (24h)</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>
            {status.summary?.avg_latency_ms
              ? `${Math.round(status.summary.avg_latency_ms)} ms`
              : "—"}
          </div>
        </div>
        <div>
          <div className="muted" style={{ fontSize: 11 }}>Probes / successes</div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>
            {status.summary?.ok_count ?? 0} / {status.summary?.total ?? 0}
          </div>
        </div>
      </div>

      {/* 24h timeline strip */}
      <div style={{ marginTop: 14 }}>
        <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
          Last 24 hours (5-minute buckets — green ok, red down, amber partial, dim no data)
        </div>
        <div style={{
          display: "flex", height: 18, borderRadius: 3, overflow: "hidden",
          border: "1px solid #333",
        }}>
          {cells.map((c) => (
            <div
              key={c.ts}
              title={`${new Date(c.ts).toLocaleTimeString()} — ${c.state}${c.total ? ` (${c.ok}/${c.total} ok)` : ""}`}
              style={{ flex: 1, background: cellColor[c.state] }}
            />
          ))}
        </div>
        <div style={{
          display: "flex", justifyContent: "space-between",
          fontSize: 10, color: "var(--muted)", marginTop: 2,
        }}>
          <span>24h ago</span>
          <span>now</span>
        </div>
      </div>

      {/* Latest per-target detail */}
      {status.latest?.probes?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
            Latest probe cycle
          </div>
          <table className="kv-table" style={{ width: "100%" }}>
            <tbody>
              {status.latest.probes.map((p) => (
                <tr key={p.target}>
                  <td>{targetLabel(p.target)}</td>
                  <td style={{ color: p.ok ? "#3fb950" : "#f85149" }}>
                    {p.ok ? "ok" : "fail"}
                  </td>
                  <td className="muted">
                    {p.latency_ms != null ? `${p.latency_ms} ms` : "—"}
                  </td>
                  <td className="muted" style={{ fontSize: 11 }}>
                    {p.error || ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Recent outages */}
      <div style={{ marginTop: 14 }}>
        <h4 style={{ margin: "0 0 6px", fontSize: 13, color: "var(--muted)" }}>
          Recent outages
        </h4>
        {outages.length === 0 ? (
          <div className="empty">No outages recorded yet.</div>
        ) : (
          <table className="kv-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th align="left">Started</th>
                <th align="left">Ended</th>
                <th align="left">Duration</th>
                <th align="left">Notified</th>
              </tr>
            </thead>
            <tbody>
              {outages.map((o) => (
                <tr key={o.id}>
                  <td>{fmtWhen(o.started_ts)}</td>
                  <td>{o.ended_ts ? fmtWhen(o.ended_ts) : <em>in progress</em>}</td>
                  <td>
                    {o.ended_ts
                      ? fmtDuration(o.duration_seconds)
                      : fmtDuration((status.now_ms - o.started_ts) / 1000)}
                  </td>
                  <td className="muted">{o.notified ? "yes" : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
