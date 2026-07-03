import React, { useEffect, useState, useCallback, useMemo } from "react";
import { api, setToken } from "../api.js";
// Reuse the same widget renderers as the desktop tab
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
import PropertyTaxWidget from "./widgets/PropertyTaxWidget.jsx";
import ReturnCountdownWidget from "./widgets/ReturnCountdownWidget.jsx";
import WhaleSeasonWidget from "./widgets/WhaleSeasonWidget.jsx";
import SeaTempWidget from "./widgets/SeaTempWidget.jsx";
import BajaRacesWidget from "./widgets/BajaRacesWidget.jsx";
import ContactsWidget from "./widgets/ContactsWidget.jsx";
import ShoppingListWidget from "./widgets/ShoppingListWidget.jsx";
import BorderLogWidget from "./widgets/BorderLogWidget.jsx";
import SpanishWidget from "./widgets/SpanishWidget.jsx";
import CostcoFuelWidget from "./widgets/CostcoFuelWidget.jsx";
import ConsumptionYoYWidget from "./widgets/ConsumptionYoYWidget.jsx";
import TodoWidget from "./widgets/TodoWidget.jsx";
import SubscriptionsWidget from "./widgets/SubscriptionsWidget.jsx";
import DabPumpWidget from "./widgets/DabPumpWidget.jsx";
import DabPumpControlWidget from "./widgets/DabPumpControlWidget.jsx";

const RENDERERS = {
  tides: TideWidget, border: BorderWidget, hoa: HoaWidget,
  quakes: QuakesWidget, storms: StormsWidget, uv_heat: UvHeatWidget,
  marine: MarineWidget, sun_moon: SunMoonWidget,
  currency: CurrencyWidget, drive_time: DriveTimeWidget,
  holidays: HolidaysWidget, solar_excess: SolarExcessWidget,
  precool: PrecoolWidget, hoa_newsletter: NewsletterWidget,
  weather: WeatherWidget, aqi: AqiWidget,
  quicklinks: QuickLinksWidget, fishing_window: FishingWindowWidget,
  reservations: ReservationsWidget, news: NewsWidget,
  property_mode: PropertyModeWidget, trip_planner: TripPlannerWidget,
  property_tax: PropertyTaxWidget, return_countdown: ReturnCountdownWidget,
  whale_season: WhaleSeasonWidget, sea_temp: SeaTempWidget,
  baja_races: BajaRacesWidget, contacts: ContactsWidget,
  shopping_list: ShoppingListWidget, border_log: BorderLogWidget,
  spanish: SpanishWidget, costco_fuel: CostcoFuelWidget,
  consumption_yoy: ConsumptionYoYWidget, todo: TodoWidget,
  dab_pump: DabPumpWidget, dab_pump_control: DabPumpControlWidget,
};

// Same tab ordering as desktop
const TAB_ORDER = [
  "Today", "Safety", "Outdoor", "Travel", "Solar", "Community", "Lists", "Local",
];
function tabSortKey(t) {
  const i = TAB_ORDER.indexOf(t);
  return i === -1 ? 999 : i;
}

function MobileCard({ widget, tzOffsetMinutes, onRefreshed }) {
  const Renderer = RENDERERS[widget.meta?.kind];
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={`m-card ${collapsed ? "m-collapsed" : ""}`}>
      <div className="m-card-head" onClick={() => setCollapsed(!collapsed)}>
        <span className="m-card-title">{widget.meta?.name}</span>
        <span className="m-card-toggle">{collapsed ? "▸" : "▾"}</span>
      </div>
      {!collapsed && (
        <div className="m-card-body">
          {Renderer ? (
            <Renderer
              data={widget.data}
              tzOffsetMinutes={tzOffsetMinutes}
              onChanged={onRefreshed}
            />
          ) : widget.id === "_events" ? (
            <EventsWidget />
          ) : widget.id === "_subscriptions" ? (
            <SubscriptionsWidget />
          ) : (
            <pre style={{ overflow: "auto", maxHeight: 200 }}>
              {JSON.stringify(widget.data, null, 2)}
            </pre>
          )}
          {widget.error && (
            <div className="error-inline">{widget.error}</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MobileApp({ session, onLoggedOut, onExitMobile, onEnterRotation, theme, onToggleTheme }) {
  const [widgets, setWidgets] = useState(null);
  const [tzOffsetMinutes, setTzOffsetMinutes] = useState(null);
  const [activeTab, setActiveTab] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, s] = await Promise.all([api.listWidgets(), api.settings()]);
      setWidgets(r.widgets || []);
      setTzOffsetMinutes(s.tz_offset_minutes ?? null);
      setErr("");
    } catch (ex) {
      if (ex.status === 401) { setToken(null); onLoggedOut(); return; }
      setErr(ex.message || "load failed");
    }
  }, [onLoggedOut]);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  const { tabs, byTab } = useMemo(() => {
    if (widgets === null) return { tabs: [], byTab: new Map() };
    const virtual = [
      { id: "_events",
        meta: { kind: "_events", name: "Today's events" },
        layout: { tab: "Community", position: 5 } },
      { id: "_subscriptions",
        meta: { kind: "_subscriptions", name: "Alert rules" },
        layout: { tab: "Lists", position: 5 } },
    ];
    const all = [...virtual, ...widgets];
    const byTab = new Map();
    for (const w of all) {
      const t = w.layout?.tab || w.meta?.default_tab || "Local";
      if (!byTab.has(t)) byTab.set(t, []);
      byTab.get(t).push(w);
    }
    for (const list of byTab.values()) {
      list.sort((a, b) => (a.layout?.position ?? 100) - (b.layout?.position ?? 100));
    }
    return {
      tabs: [...byTab.keys()].sort((a, b) => tabSortKey(a) - tabSortKey(b)),
      byTab,
    };
  }, [widgets]);

  useEffect(() => {
    if (!activeTab && tabs.length > 0) setActiveTab(tabs[0]);
  }, [tabs, activeTab]);

  if (err) return <div className="m-error">{err}</div>;
  if (widgets === null) return <div className="m-loading">Loading…</div>;

  const active = activeTab && tabs.includes(activeTab) ? activeTab : tabs[0];
  const list = byTab.get(active) || [];

  return (
    <div className="m-app">
      <header className="m-header">
        <span className="m-brand">SolarSage</span>
        <span className="m-tab-label">{active}</span>
        <span style={{ display: "flex", gap: 4 }}>
          {onToggleTheme && (
            <button className="m-menu-btn" onClick={onToggleTheme} title="Toggle theme">
              {theme === "light" ? "🌙" : "☀"}
            </button>
          )}
          {onEnterRotation && (
            <button className="m-menu-btn" onClick={onEnterRotation} title="Fullscreen rotation">
              📺
            </button>
          )}
          <button className="m-menu-btn" onClick={onExitMobile} title="Desktop view">
            🖥
          </button>
        </span>
      </header>
      <main className="m-main">
        {list.map((w) => (
          <MobileCard
            key={w.id}
            widget={w}
            tzOffsetMinutes={tzOffsetMinutes}
            onRefreshed={load}
          />
        ))}
      </main>
      <nav className="m-tabbar">
        {tabs.map((t) => (
          <button
            key={t}
            className={`m-tab ${t === active ? "active" : ""}`}
            onClick={() => setActiveTab(t)}
          >
            {t}
          </button>
        ))}
      </nav>
    </div>
  );
}
