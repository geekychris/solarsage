import React, { useEffect, useState, useCallback, useMemo } from "react";
import { api } from "../api.js";
import TideWidget from "./widgets/TideWidget.jsx";
import BorderWidget from "./widgets/BorderWidget.jsx";
import HoaWidget from "./widgets/HoaWidget.jsx";
import EventsWidget from "./widgets/EventsWidget.jsx";
import QuakesWidget from "./widgets/QuakesWidget.jsx";
import StormsWidget from "./widgets/StormsWidget.jsx";
import UvHeatWidget from "./widgets/UvHeatWidget.jsx";
import MarineWidget from "./widgets/MarineWidget.jsx";
import SunMoonWidget from "./widgets/SunMoonWidget.jsx";
import CurrencyWidget from "./widgets/CurrencyWidget.jsx";
import DriveTimeWidget from "./widgets/DriveTimeWidget.jsx";
import HolidaysWidget from "./widgets/HolidaysWidget.jsx";
import SolarExcessWidget from "./widgets/SolarExcessWidget.jsx";
import PrecoolWidget from "./widgets/PrecoolWidget.jsx";
import NewsletterWidget from "./widgets/NewsletterWidget.jsx";
import WeatherWidget from "./widgets/WeatherWidget.jsx";
import AqiWidget from "./widgets/AqiWidget.jsx";
import QuickLinksWidget from "./widgets/QuickLinksWidget.jsx";
import FishingWindowWidget from "./widgets/FishingWindowWidget.jsx";
import ReservationsWidget from "./widgets/ReservationsWidget.jsx";
import NewsWidget from "./widgets/NewsWidget.jsx";
import PropertyModeWidget from "./widgets/PropertyModeWidget.jsx";
import TripPlannerWidget from "./widgets/TripPlannerWidget.jsx";
import WidgetSettings from "./WidgetSettings.jsx";

const RENDERERS = {
  tides: TideWidget,
  border: BorderWidget,
  hoa: HoaWidget,
  quakes: QuakesWidget,
  storms: StormsWidget,
  uv_heat: UvHeatWidget,
  marine: MarineWidget,
  sun_moon: SunMoonWidget,
  currency: CurrencyWidget,
  drive_time: DriveTimeWidget,
  holidays: HolidaysWidget,
  solar_excess: SolarExcessWidget,
  precool: PrecoolWidget,
  hoa_newsletter: NewsletterWidget,
  weather: WeatherWidget,
  aqi: AqiWidget,
  quicklinks: QuickLinksWidget,
  fishing_window: FishingWindowWidget,
  reservations: ReservationsWidget,
  news: NewsWidget,
  property_mode: PropertyModeWidget,
  trip_planner: TripPlannerWidget,
};

// Stable order for subtabs when more than one is present.
const TAB_ORDER = [
  "Today", "Safety", "Outdoor", "Travel", "Solar", "Community", "Local",
];

function tabSortKey(t) {
  const i = TAB_ORDER.indexOf(t);
  return i === -1 ? 999 : i;
}

function FetchedAt({ ts, error }) {
  if (error) return <span className="error-inline">error: {error}</span>;
  if (!ts) return <span className="muted">never</span>;
  return <span className="muted">fetched {new Date(ts * 1000).toLocaleTimeString()}</span>;
}

function MoveControls({ widget, allTabs, onMove }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="widget-move">
      <button title="Move up" onClick={() => onMove(widget.id, { delta: -1 })}>↑</button>
      <button title="Move down" onClick={() => onMove(widget.id, { delta: +1 })}>↓</button>
      <div className="widget-move-tab">
        <button onClick={() => setOpen((o) => !o)} title="Move to tab">⇄</button>
        {open && (
          <div className="widget-move-menu">
            {allTabs.map((t) => (
              <button
                key={t}
                disabled={t === widget.layout.tab}
                onClick={() => { setOpen(false); onMove(widget.id, { tab: t }); }}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function WidgetCard({ widget, tzOffsetMinutes, onRefreshed, allTabs, onMove }) {
  const Renderer = RENDERERS[widget.meta.kind];
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      await api.refreshWidget(widget.id);
      onRefreshed();
    } finally {
      setBusy(false);
    }
  }, [widget.id, onRefreshed]);

  return (
    <div className="panel widget-card">
      <div className="widget-head">
        <div className="widget-title">
          <h3 style={{ margin: 0 }}>{widget.meta.name}</h3>
          <span
            className="info-icon"
            title={widget.meta.description}
            aria-label="About this widget"
          >ⓘ</span>
        </div>
        <div className="widget-head-meta">
          <FetchedAt ts={widget.fetched_at} error={widget.error} />
          <button onClick={refresh} disabled={busy} title="Refresh now">
            {busy ? "…" : "↻"}
          </button>
          <button onClick={() => setSettingsOpen(true)} title="Settings">⚙</button>
          <MoveControls widget={widget} allTabs={allTabs} onMove={onMove} />
        </div>
      </div>
      <div className="widget-body">
        {Renderer ? (
          <Renderer data={widget.data} tzOffsetMinutes={tzOffsetMinutes} />
        ) : (
          <pre style={{ overflow: "auto", maxHeight: 200 }}>
            {JSON.stringify(widget.data, null, 2)}
          </pre>
        )}
      </div>
      {settingsOpen && (
        <WidgetSettings
          widget={widget}
          onClose={() => setSettingsOpen(false)}
          onSaved={onRefreshed}
        />
      )}
    </div>
  );
}

export default function LocalTab({ tzOffsetMinutes }) {
  const [widgets, setWidgets] = useState(null);
  const [err, setErr] = useState("");
  const [activeSubTab, setActiveSubTab] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await api.listWidgets();
      setWidgets(r.widgets || []);
      setErr("");
    } catch (ex) {
      setErr(ex.message || "failed to load widgets");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  // The Events card is a pinned, server-side "virtual" card that lives
  // in Community by default. We carry it through the same tab system so
  // users can move it like any other widget — but we don't go through
  // /api/widgets for its data.
  const widgetsWithEvents = useMemo(() => {
    if (widgets === null) return null;
    const evRow = {
      id: "_events",
      meta: {
        kind: "_events",
        name: "Today's events",
        description:
          "HOA activities (auto-extracted) and manual events. Reminders fire through the pi5 speaker.",
      },
      layout: { tab: "Community", position: 5 },
      fetched_at: null,
      error: null,
      data: null,
    };
    return [evRow, ...widgets];
  }, [widgets]);

  const tabsAndGroups = useMemo(() => {
    if (!widgetsWithEvents) return { tabs: [], byTab: new Map() };
    const byTab = new Map();
    for (const w of widgetsWithEvents) {
      const t = w.layout?.tab || w.meta?.default_tab || "Local";
      if (!byTab.has(t)) byTab.set(t, []);
      byTab.get(t).push(w);
    }
    for (const list of byTab.values()) {
      list.sort((a, b) => (a.layout?.position ?? 100) - (b.layout?.position ?? 100));
    }
    const tabs = [...byTab.keys()].sort(
      (a, b) => tabSortKey(a) - tabSortKey(b),
    );
    return { tabs, byTab };
  }, [widgetsWithEvents]);

  useEffect(() => {
    if (!activeSubTab && tabsAndGroups.tabs.length > 0) {
      setActiveSubTab(tabsAndGroups.tabs[0]);
    } else if (activeSubTab && !tabsAndGroups.tabs.includes(activeSubTab) && tabsAndGroups.tabs.length > 0) {
      setActiveSubTab(tabsAndGroups.tabs[0]);
    }
  }, [tabsAndGroups.tabs, activeSubTab]);

  const onMove = useCallback(async (widgetId, { delta, tab }) => {
    if (widgetId === "_events") return; // virtual card, not server-side
    const current = (widgets || []).find((w) => w.id === widgetId);
    if (!current) return;
    const body = {};
    if (tab) body.tab = tab;
    if (typeof delta === "number") {
      const pos = (current.layout?.position ?? 100) + delta * 10;
      body.position = pos;
    }
    try {
      await fetch(`/api/widgets/${encodeURIComponent(widgetId)}/layout`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(localStorage.getItem("eg4.token")
            ? { Authorization: `Bearer ${localStorage.getItem("eg4.token")}` }
            : {}),
        },
        body: JSON.stringify(body),
      });
    } finally {
      load();
    }
  }, [widgets, load]);

  if (err) return <div className="error">{err}</div>;
  if (widgetsWithEvents === null) return <div className="muted">Loading widgets…</div>;
  const { tabs, byTab } = tabsAndGroups;
  if (tabs.length === 0) {
    return <div className="muted">No widgets registered.</div>;
  }
  const active = activeSubTab && tabs.includes(activeSubTab) ? activeSubTab : tabs[0];
  const widgetsInTab = byTab.get(active) || [];

  return (
    <div className="local-wrap">
      <div className="local-subtabs">
        {tabs.map((t) => (
          <div
            key={t}
            className={`local-subtab ${t === active ? "active" : ""}`}
            onClick={() => setActiveSubTab(t)}
          >
            {t}
            <span className="muted" style={{ marginLeft: 6, fontSize: 11 }}>
              {(byTab.get(t) || []).length}
            </span>
          </div>
        ))}
      </div>
      <div className="local-grid">
        {widgetsInTab.map((w) => (
          w.id === "_events" ? (
            <div key="_events" className="panel widget-card">
              <div className="widget-head">
                <div className="widget-title">
                  <h3 style={{ margin: 0 }}>{w.meta.name}</h3>
                  <span
                    className="info-icon"
                    title={w.meta.description}
                    aria-label="About"
                  >ⓘ</span>
                </div>
                <div className="widget-head-meta">
                  <span className="muted" style={{ fontSize: 11 }}>pinned</span>
                </div>
              </div>
              <div className="widget-body">
                <EventsWidget />
              </div>
            </div>
          ) : (
            <WidgetCard
              key={w.id}
              widget={w}
              tzOffsetMinutes={tzOffsetMinutes}
              onRefreshed={load}
              allTabs={tabs}
              onMove={onMove}
            />
          )
        ))}
      </div>
    </div>
  );
}
