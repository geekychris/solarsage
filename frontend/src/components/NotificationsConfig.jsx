import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const SOURCE_META = {
  tides: {
    label: "Tides",
    hint: "Announce upcoming high / low tides for configured stations.",
    supportsTypes: true,
    stationsHint: "Leave empty to include every station configured on the tides widget.",
  },
  hoa: {
    label: "HOA events",
    hint: "Community activities from the weekly PDF.",
  },
  storms: {
    label: "Storms",
    hint: "Named tropical systems that could affect San Felipe.",
  },
  quakes: {
    label: "Earthquakes",
    hint: "USGS quakes above a minimum magnitude within the widget's radius.",
    supportsMagnitude: true,
  },
  battery_charged: {
    label: "Battery charged",
    hint: "Announce when the battery crosses a full-charge threshold.",
    supportsSocThresholds: true,
  },
  excessive_discharge: {
    label: "Excessive discharge",
    hint: "Announce when the battery discharges above a kW threshold for a sustained window.",
    supportsDischargeThresholds: true,
  },
  water_low: {
    label: "Water tank low",
    hint: "Announce when the tank crosses each configured percent-full threshold going down.",
    supportsWaterThresholds: true,
  },
};

const CHANNEL_OPTIONS = [
  { id: "tts", label: "TTS" },
  { id: "telegram", label: "Telegram" },
];

function parseOffsets(s) {
  return String(s || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
    .map((t) => Number(t))
    .filter((n) => Number.isFinite(n) && n >= 0);
}

function formatOffsets(list) {
  return (list || []).join(", ");
}

export default function NotificationsConfig() {
  const [config, setConfig] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const r = await api.getAnnouncements();
        setConfig(r.config || {});
      } catch (ex) {
        setErr(ex.message);
      }
    })();
  }, []);

  function updateSource(src, patch) {
    setConfig((cur) => ({ ...cur, [src]: { ...(cur[src] || {}), ...patch } }));
    setSaved("");
  }

  function toggleChannel(src, ch) {
    const cur = new Set(config[src]?.channels || []);
    if (cur.has(ch)) cur.delete(ch); else cur.add(ch);
    updateSource(src, { channels: Array.from(cur) });
  }

  function toggleType(src, t) {
    const cur = new Set(config[src]?.types || []);
    if (cur.has(t)) cur.delete(t); else cur.add(t);
    updateSource(src, { types: Array.from(cur) });
  }

  async function save() {
    setBusy(true);
    setErr("");
    try {
      const r = await api.putAnnouncements(config);
      setConfig(r.config || config);
      setSaved("Saved.");
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  async function ingestNow() {
    setBusy(true);
    setErr("");
    try {
      const r = await api.ingestAnnouncements();
      const totals = Object.entries(r.ingested || {})
        .map(([k, v]) => `${k}: ${v}`)
        .join("  ");
      setSaved(`Ingested — ${totals}`);
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  if (!config) {
    return <div className="muted">Loading…</div>;
  }

  const sources = Object.keys(SOURCE_META);
  for (const k of Object.keys(config)) if (!sources.includes(k)) sources.push(k);

  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
        Per-source auto-announcements. Warnings fire via the configured channels
        at the listed minutes-before offsets (e.g. <code>120, 30</code> = two
        alerts: 2 h and 30 min ahead).
      </div>
      {err && <div className="error">{err}</div>}
      {saved && <div className="muted" style={{ color: "var(--ok)" }}>{saved}</div>}

      {sources.map((src) => {
        const meta = SOURCE_META[src] || { label: src, hint: "" };
        const cfg = config[src] || {};
        return (
          <div
            key={src}
            className="notif-source"
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 12,
              marginBottom: 10,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <label
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  fontWeight: 600, cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={!!cfg.enabled}
                  onChange={(e) => updateSource(src, { enabled: e.target.checked })}
                />
                {meta.label}
              </label>
              <span className="muted" style={{ fontSize: 12 }}>{meta.hint}</span>
            </div>

            {cfg.enabled && (
              <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                {!(meta.supportsSocThresholds
                  || meta.supportsDischargeThresholds
                  || meta.supportsWaterThresholds) && (
                  <div className="field">
                    <label>Warn (minutes before, comma-separated)</label>
                    <input
                      value={formatOffsets(cfg.warn_minutes_before)}
                      onChange={(e) =>
                        updateSource(src, {
                          warn_minutes_before: parseOffsets(e.target.value),
                        })
                      }
                      placeholder="120, 30"
                    />
                  </div>
                )}
                {meta.supportsSocThresholds && (
                  <>
                    <div className="field">
                      <label>Announce at (SoC %)</label>
                      <input
                        type="number" min="1" max="100" step="1"
                        value={cfg.threshold_soc ?? 98}
                        onChange={(e) => updateSource(src, {
                          threshold_soc: Number(e.target.value),
                        })}
                      />
                    </div>
                    <div className="field">
                      <label>Rearm below (SoC %)</label>
                      <input
                        type="number" min="0" max="100" step="1"
                        value={cfg.rearm_below_soc ?? 85}
                        onChange={(e) => updateSource(src, {
                          rearm_below_soc: Number(e.target.value),
                        })}
                      />
                      <span className="muted" style={{ fontSize: 11 }}>
                        Prevents re-firing every minute — SoC has to drop
                        this low before the "charged" alert re-arms.
                      </span>
                    </div>
                  </>
                )}
                {meta.supportsDischargeThresholds && (
                  <>
                    <div className="field">
                      <label>Announce when discharge exceeds (kW)</label>
                      <input
                        type="number" min="0" step="0.1"
                        value={cfg.threshold_kw ?? 3.0}
                        onChange={(e) => updateSource(src, {
                          threshold_kw: Number(e.target.value),
                        })}
                      />
                    </div>
                    <div className="field">
                      <label>Rearm below (kW)</label>
                      <input
                        type="number" min="0" step="0.1"
                        value={cfg.rearm_below_kw ?? 1.5}
                        onChange={(e) => updateSource(src, {
                          rearm_below_kw: Number(e.target.value),
                        })}
                      />
                    </div>
                    <div className="field">
                      <label>Must be sustained for (seconds)</label>
                      <input
                        type="number" min="0" step="10"
                        value={cfg.min_sustained_seconds ?? 90}
                        onChange={(e) => updateSource(src, {
                          min_sustained_seconds: Number(e.target.value),
                        })}
                      />
                      <span className="muted" style={{ fontSize: 11 }}>
                        Avoids announcing a brief compressor kick.
                      </span>
                    </div>
                  </>
                )}
                {meta.supportsWaterThresholds && (
                  <div className="field">
                    <label>Warn at (percent-full, comma-separated)</label>
                    <input
                      value={(cfg.warn_percents || []).join(", ")}
                      onChange={(e) => updateSource(src, {
                        warn_percents: parseOffsets(e.target.value),
                      })}
                      placeholder="50, 25, 10"
                    />
                    <span className="muted" style={{ fontSize: 11 }}>
                      Each threshold fires once when crossed going down,
                      re-arms 5% above.
                    </span>
                  </div>
                )}
                <div className="field">
                  <label>Channels</label>
                  <div style={{ display: "flex", gap: 12 }}>
                    {CHANNEL_OPTIONS.map((c) => (
                      <label key={c.id} style={{ display: "flex", gap: 4 }}>
                        <input
                          type="checkbox"
                          checked={(cfg.channels || []).includes(c.id)}
                          onChange={() => toggleChannel(src, c.id)}
                        />
                        {c.label}
                      </label>
                    ))}
                  </div>
                </div>
                {meta.supportsTypes && (
                  <div className="field">
                    <label>Tide types</label>
                    <div style={{ display: "flex", gap: 12 }}>
                      {["high", "low"].map((t) => (
                        <label key={t} style={{ display: "flex", gap: 4 }}>
                          <input
                            type="checkbox"
                            checked={(cfg.types || ["high", "low"]).includes(t)}
                            onChange={() => toggleType(src, t)}
                          />
                          {t}
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                {meta.supportsTypes && (
                  <div className="field">
                    <label>Stations (comma-separated ids, empty = all)</label>
                    <input
                      value={(cfg.stations || []).join(", ")}
                      onChange={(e) =>
                        updateSource(src, {
                          stations: e.target.value
                            .split(",")
                            .map((t) => t.trim())
                            .filter(Boolean),
                        })
                      }
                      placeholder="san_felipe, puertecitos"
                    />
                    <span className="muted" style={{ fontSize: 11 }}>
                      {meta.stationsHint}
                    </span>
                  </div>
                )}
                {meta.supportsMagnitude && (
                  <div className="field">
                    <label>Min magnitude</label>
                    <input
                      type="number"
                      step="0.1"
                      value={cfg.min_magnitude ?? 4.5}
                      onChange={(e) =>
                        updateSource(src, {
                          min_magnitude: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 12 }}>
        <button type="button" onClick={ingestNow} disabled={busy}>
          Ingest now
        </button>
        <button
          type="button"
          className="primary"
          onClick={save}
          disabled={busy}
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
