import React, { useEffect, useState } from "react";
import { api, setToken } from "../api.js";
import LiveTiles from "./LiveTiles.jsx";
import RawDataTable from "./RawDataTable.jsx";
import HistoryChart from "./HistoryChart.jsx";
import TodayChart from "./TodayChart.jsx";
import BatteryForecast from "./BatteryForecast.jsx";
import BatteryCycle from "./BatteryCycle.jsx";
import Settings from "./Settings.jsx";
import RangeChart from "./RangeChart.jsx";
import ExcessChart from "./ExcessChart.jsx";
import WeatherPanel from "./WeatherPanel.jsx";
import SyncButton from "./SyncButton.jsx";
import SitesPanel from "./SitesPanel.jsx";
import AppliancesPanel from "./AppliancesPanel.jsx";
import SchedulerPanel from "./SchedulerPanel.jsx";
import Heatmap from "./Heatmap.jsx";
import AlertsPanel from "./AlertsPanel.jsx";
import HealthPanel from "./HealthPanel.jsx";

const POLL_LIVE_MS = 15_000;

export default function Dashboard({ session, onLoggedOut }) {
  const [inverters, setInverters] = useState([]);
  const [selected, setSelected] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [err, setErr] = useState("");
  const [lastUpdate, setLastUpdate] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsBump, setSettingsBump] = useState(0);
  const [tzOffsetMinutes, setTzOffsetMinutes] = useState(null);
  const [siteId, setSiteId] = useState(null);
  const [activeTab, setActiveTab] = useState("now");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [r, s] = await Promise.all([api.inverters(), api.settings()]);
        if (cancelled) return;
        setInverters(r.inverters || []);
        if ((r.inverters || []).length > 0) {
          setSelected(r.inverters[0].serialNum);
        }
        setTzOffsetMinutes(s.tz_offset_minutes ?? null);
      } catch (ex) {
        if (ex.status === 401) {
          setToken(null);
          onLoggedOut();
          return;
        }
        setErr(ex.message);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [onLoggedOut, settingsBump]);

  // Today in the inverter's local timezone (YYYY-MM-DD)
  const todayLocal = (() => {
    if (tzOffsetMinutes == null) return null;
    const nowUtc = Date.now();
    const local = new Date(nowUtc + tzOffsetMinutes * 60_000);
    return local.toISOString().slice(0, 10);
  })();

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    async function pull() {
      try {
        const r = await api.snapshot(selected);
        if (cancelled) return;
        setSnapshot(r);
        setLastUpdate(new Date(r.ts));
        setErr("");
      } catch (ex) {
        if (!cancelled) setErr(ex.message);
      }
    }
    pull();
    const id = setInterval(pull, POLL_LIVE_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [selected]);

  async function logout(forget = false) {
    try {
      await api.logout(forget);
    } catch {
      /* ignore */
    }
    setToken(null);
    onLoggedOut();
  }

  const selectedInv = inverters.find((i) => i.serialNum === selected);

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <img src="/solarsage.png" alt="SolarSage" className="brand-logo" />
          <h1>SolarSage</h1>
        </div>
        <div className="meta">
          <SyncButton
            serial={selected}
            onSynced={() => setSettingsBump((n) => n + 1)}
          />
          {lastUpdate && <span>updated {lastUpdate.toLocaleTimeString()}</span>}
          <span>{session.username}</span>
          <button onClick={() => window.print()} title="Print or save as PDF" className="no-print">Print</button>
          <button onClick={() => setSettingsOpen(true)}>Settings</button>
          <button onClick={() => logout(false)}>Sign out</button>
          <button
            onClick={() => {
              if (confirm("Forget saved credentials? Backend will stop auto-login on restart."))
                logout(true);
            }}
            title="Sign out and delete saved credentials"
          >
            Forget
          </button>
        </div>
      </div>
      <div className="dashboard">
        <div className="sidebar">
          <SitesPanel selected={siteId} onSelect={setSiteId} refreshKey={settingsBump} />
          <h3 style={{ marginTop: 16 }}>Inverters</h3>
          {inverters.length === 0 && <div className="muted">none</div>}
          {inverters.map((inv) => (
            <div
              key={inv.serialNum}
              className={`inverter-item ${inv.serialNum === selected ? "active" : ""}`}
              onClick={() => setSelected(inv.serialNum)}
              title={`${inv.plantName || ""} · ${inv.fwVersion || ""}`}
            >
              <div>{inv.serialNum}</div>
              <div className="muted" style={{ fontSize: 11 }}>{inv.plantName}</div>
            </div>
          ))}
        </div>
        <div className="main">
          {err && <div className="error">{err}</div>}

          <div className="tabs no-print">
            {[
              ["now", "Now"],
              ["today", "Today"],
              ["battery", "Battery"],
              ["history", "History"],
              ["health", "Health & Alerts"],
              ["all", "All"],
            ].map(([id, label]) => (
              <div
                key={id}
                className={`tab ${activeTab === id ? "active" : ""}`}
                onClick={() => setActiveTab(id)}
              >
                {label}
              </div>
            ))}
          </div>

          <div className={`tab-section ${activeTab === "now" || activeTab === "all" ? "active" : ""}`}>
            {selectedInv && (
              <div className="panel">
                <h3>{selectedInv.plantName || selectedInv.serialNum}</h3>
                <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
                  SN {selectedInv.serialNum} · FW {selectedInv.fwVersion || "—"} · {selectedInv.phase || ""}
                </div>
                <LiveTiles snapshot={snapshot} />
              </div>
            )}
            {selected && <WeatherPanel key={`wp-${selected}-${settingsBump}`} serial={selected} />}
            {snapshot && (
              <div className="panel">
                <h3>Raw data</h3>
                <RawDataTable snapshot={snapshot} />
              </div>
            )}
          </div>

          <div className={`tab-section ${activeTab === "today" || activeTab === "all" ? "active" : ""}`}>
            {selected && <TodayChart key={`tc-${selected}-${settingsBump}`} serial={selected} />}
            {selected && <ExcessChart key={`ec-${selected}-${settingsBump}`} serial={selected} />}
            {selected && siteId && (
              <SchedulerPanel key={`sch-${selected}-${siteId}`} serial={selected} siteId={siteId} />
            )}
          </div>

          <div className={`tab-section ${activeTab === "battery" || activeTab === "all" ? "active" : ""}`}>
            {selected && <BatteryForecast key={`bf-${selected}-${settingsBump}`} serial={selected} />}
            {selected && <BatteryCycle key={`bc-${selected}-${settingsBump}`} serial={selected} />}
          </div>

          <div className={`tab-section ${activeTab === "history" || activeTab === "all" ? "active" : ""}`}>
            {selected && (
              <RangeChart
                key={`rc-${selected}-${settingsBump}`}
                serial={selected}
                tzOffsetMinutes={tzOffsetMinutes}
              />
            )}
            {selected && <Heatmap key={`hm-${selected}-${settingsBump}`} serial={selected} />}
            {selected && <HistoryChart serial={selected} />}
          </div>

          <div className={`tab-section ${activeTab === "health" || activeTab === "all" ? "active" : ""}`}>
            {selected && <HealthPanel key={`hp-${selected}-${settingsBump}`} serial={selected} />}
            {siteId && <AlertsPanel key={`al-${siteId}`} siteId={siteId} />}
            {siteId && <AppliancesPanel key={`ap-${siteId}`} siteId={siteId} />}
          </div>
        </div>
      </div>
      <Settings
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => setSettingsBump((n) => n + 1)}
      />
    </div>
  );
}
