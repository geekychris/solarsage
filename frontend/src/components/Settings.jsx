import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import RotationConfigWidget from "./widgets/RotationConfigWidget.jsx";
import NotificationsConfig from "./NotificationsConfig.jsx";
import HaIntegrationsConfig from "./HaIntegrationsConfig.jsx";
import LocationPicker from "./LocationPicker.jsx";

const TABS = [
  { id: "system", label: "System" },
  { id: "rotation", label: "Rotation" },
  { id: "notifications", label: "Notifications" },
  { id: "ha", label: "HA Integrations" },
];

const KNOWN_TABS = ["Today", "Safety", "Outdoor", "Travel", "Solar", "Community", "Lists", "Local"];

function TabLabelsEditor({ value, onChange }) {
  function set(tab, label) {
    const next = { ...value };
    if (label && label !== tab) next[tab] = label;
    else delete next[tab];
    onChange(next);
  }
  return (
    <table className="tab-labels-editor">
      <thead>
        <tr>
          <th>Internal name</th>
          <th>Display label</th>
        </tr>
      </thead>
      <tbody>
        {KNOWN_TABS.map((t) => (
          <tr key={t}>
            <td><code>{t}</code></td>
            <td>
              <input
                value={value[t] ?? ""}
                placeholder={t}
                onChange={(e) => set(t, e.target.value)}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SecretInput({ value, onChange, placeholder, name }) {
  const [show, setShow] = useState(false);
  return (
    <div className="secret-input">
      <input
        type={show ? "text" : "password"}
        autoComplete="off"
        name={name}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className="secret-toggle"
        title={show ? "Hide" : "Show"}
        onClick={() => setShow((v) => !v)}
      >
        {show ? "🙈" : "👁"}
      </button>
    </div>
  );
}

export default function Settings({ open, onClose, onSaved }) {
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState("system");

  useEffect(() => {
    if (!open) return;
    (async () => {
      try {
        setS(await api.settings());
      } catch (ex) {
        setErr(ex.message);
      }
    })();
  }, [open]);

  if (!open) return null;
  if (!s) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <div className="muted">Loading…</div>
        </div>
      </div>
    );
  }

  function up(k, v) {
    setS((cur) => ({ ...cur, [k]: v }));
  }

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      const out = await api.updateSettings({
        lat: Number(s.lat),
        lon: Number(s.lon),
        tz: s.tz,
        peak_kw: Number(s.peak_kw),
        battery_capacity_kwh: Number(s.battery_capacity_kwh),
        max_charge_kw: Number(s.max_charge_kw),
        history_days: Number(s.history_days),
        ha_url: s.ha_url ?? "",
        ha_token: s.ha_token ?? "",
        tts_url: s.tts_url ?? "",
        notify_telegram_service: s.notify_telegram_service ?? "",
        notify_telegram_target: s.notify_telegram_target ?? "",
        worldtides_api_key: s.worldtides_api_key ?? "",
        eia_api_key: s.eia_api_key ?? "",
        tab_labels: s.tab_labels ?? {},
      });
      onSaved(out);
      onClose();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`settings-tab ${active === t.id ? "active" : ""}`}
              onClick={() => setActive(t.id)}
            >
              {t.label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <button
            type="button"
            className="settings-tab-close"
            onClick={onClose}
            title="Close"
          >✕</button>
        </div>

        {active === "system" && (
          <form onSubmit={save}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Used by the forecast and clear-sky models. Tune to match your install.
            </div>
            {err && <div className="error">{err}</div>}
            <div className="grid-2">
              <div className="field" style={{ gridColumn: "span 2" }}>
                <label>Location</label>
                <LocationPicker
                  lat={Number(s.lat) || 31.025}
                  lon={Number(s.lon) || -114.838}
                  onChange={({ lat, lon }) => {
                    up("lat", String(lat));
                    up("lon", String(lon));
                  }}
                  height={220}
                />
                <span className="muted" style={{ fontSize: 11 }}>
                  Click or drag the marker to set. Used by weather /
                  solar-forecast / astronomy widgets that don't have
                  their own explicit lat/lon.
                </span>
              </div>
              <div className="field">
                <label>Latitude (north +)</label>
                <input value={s.lat} onChange={(e) => up("lat", e.target.value)} />
              </div>
              <div className="field">
                <label>Longitude (east +)</label>
                <input value={s.lon} onChange={(e) => up("lon", e.target.value)} />
              </div>
              <div className="field" style={{ gridColumn: "span 2" }}>
                <label>Timezone (IANA name)</label>
                <input value={s.tz} onChange={(e) => up("tz", e.target.value)} placeholder="America/Tijuana" />
                <span className="muted" style={{ fontSize: 11 }}>
                  current UTC offset: {s.tz_offset_minutes} min
                </span>
              </div>
              <div className="field">
                <label>System peak (kW DC)</label>
                <input value={s.peak_kw} onChange={(e) => up("peak_kw", e.target.value)} />
              </div>
              <div className="field">
                <label>Inverter max charge (kW)</label>
                <input value={s.max_charge_kw} onChange={(e) => up("max_charge_kw", e.target.value)} />
              </div>
              <div className="field">
                <label>Battery capacity (kWh)</label>
                <input value={s.battery_capacity_kwh} onChange={(e) => up("battery_capacity_kwh", e.target.value)} />
              </div>
              <div className="field">
                <label>History window (days)</label>
                <input value={s.history_days} onChange={(e) => up("history_days", e.target.value)} />
              </div>
            </div>

            <h4 style={{ marginTop: 20, marginBottom: 6 }}>Tab labels</h4>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
              Rename the widget tabs (Solar, Community, Local, etc.) or
              consolidate — e.g. label both "Local" and "Solar" as
              "House" and their widgets merge into one tab.
            </div>
            <TabLabelsEditor
              value={s.tab_labels ?? {}}
              onChange={(v) => up("tab_labels", v)}
            />

            <h4 style={{ marginTop: 20, marginBottom: 6 }}>External services</h4>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              URLs, tokens, and API keys for services SolarSage talks to.
              Leaving a field blank falls back to the backend's env var
              of the same uppercased name (e.g. <code>HA_URL</code>).
            </div>
            <div className="grid-2">
              <div className="field" style={{ gridColumn: "span 2" }}>
                <label>Home Assistant URL</label>
                <input
                  value={s.ha_url ?? ""}
                  placeholder="http://ha-sf.hitorro.com:8123"
                  onChange={(e) => up("ha_url", e.target.value)}
                />
              </div>
              <div className="field" style={{ gridColumn: "span 2" }}>
                <label>Home Assistant token</label>
                <SecretInput
                  name="ha_token"
                  value={s.ha_token}
                  placeholder="long-lived access token"
                  onChange={(v) => up("ha_token", v)}
                />
                <span className="muted" style={{ fontSize: 11 }}>
                  Profile → Security → Long-Lived Access Tokens in HA.
                </span>
              </div>
              <div className="field" style={{ gridColumn: "span 2" }}>
                <label>Local TTS URL</label>
                <input
                  value={s.tts_url ?? ""}
                  placeholder="http://localhost:5006/say"
                  onChange={(e) => up("tts_url", e.target.value)}
                />
              </div>
              <div className="field">
                <label>Telegram service (HA)</label>
                <input
                  value={s.notify_telegram_service ?? ""}
                  placeholder="notify.telegram"
                  onChange={(e) => up("notify_telegram_service", e.target.value)}
                />
              </div>
              <div className="field">
                <label>Telegram target (chat id)</label>
                <input
                  value={s.notify_telegram_target ?? ""}
                  placeholder="123456789 or @channel"
                  onChange={(e) => up("notify_telegram_target", e.target.value)}
                />
              </div>
              <div className="field">
                <label>WorldTides API key</label>
                <SecretInput
                  name="worldtides_api_key"
                  value={s.worldtides_api_key}
                  onChange={(v) => up("worldtides_api_key", v)}
                />
              </div>
              <div className="field">
                <label>EIA API key</label>
                <SecretInput
                  name="eia_api_key"
                  value={s.eia_api_key}
                  placeholder="DEMO_KEY (rate-limited fallback)"
                  onChange={(v) => up("eia_api_key", v)}
                />
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button type="button" onClick={onClose}>Cancel</button>
              <button className="primary" type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        )}

        {active === "rotation" && (
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Pick which widgets rotate in the fullscreen "screensaver" view
              and how long each is shown. Same widget can appear multiple
              times to weight its visibility (e.g. Solar vitals every other
              step).
            </div>
            <RotationConfigWidget />
          </div>
        )}

        {active === "notifications" && <NotificationsConfig />}

        {active === "ha" && <HaIntegrationsConfig />}
      </div>
    </div>
  );
}
