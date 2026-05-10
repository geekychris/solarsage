import React, { useState } from "react";
import { api } from "../api.js";

export default function SyncButton({ serial, onSynced }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [days, setDays] = useState(30);

  async function run() {
    if (!serial) return;
    setBusy(true);
    setErr("");
    setMsg("");
    const t0 = Date.now();
    try {
      const r = await api.sync(serial, days);
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      const okDays = r.days_with_data;
      const total = r.total_values_written.toLocaleString();
      let summary = `Synced ${okDays}/${r.days_requested} days · ${total} values in ${secs}s`;
      if (r.errors?.length) summary += ` · ${r.errors.length} errors`;
      setMsg(summary);
      onSynced?.(r);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="sync-control">
      <select value={days} onChange={(e) => setDays(Number(e.target.value))} disabled={busy}>
        <option value={7}>7d</option>
        <option value={30}>30d</option>
        <option value={90}>90d</option>
        <option value={180}>180d</option>
        <option value={365}>365d</option>
      </select>
      <button className="primary" onClick={run} disabled={busy || !serial}>
        {busy ? "Syncing…" : "Sync"}
      </button>
      {msg && <span className="sync-msg ok">{msg}</span>}
      {err && <span className="sync-msg err">{err}</span>}
    </div>
  );
}
