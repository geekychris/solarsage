import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
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
import PropertyTaxWidget from "./widgets/PropertyTaxWidget.jsx";
import ReturnCountdownWidget from "./widgets/ReturnCountdownWidget.jsx";
import WhaleSeasonWidget from "./widgets/WhaleSeasonWidget.jsx";
import SeaTempWidget from "./widgets/SeaTempWidget.jsx";
import BajaRacesWidget from "./widgets/BajaRacesWidget.jsx";
import SolarVitalsWidget from "./widgets/SolarVitalsWidget.jsx";
import ConsumptionYoYWidget from "./widgets/ConsumptionYoYWidget.jsx";

// The rotation is a read-only glance display, so we deliberately
// exclude the CRUD widgets (contacts / shopping / todo / border log /
// subscriptions) since they need editing.
const RENDERERS = {
  tides: TideWidget, border: BorderWidget, hoa: HoaWidget,
  quakes: QuakesWidget, storms: StormsWidget, uv_heat: UvHeatWidget,
  aqi: AqiWidget, weather: WeatherWidget,
  marine: MarineWidget, sun_moon: SunMoonWidget,
  fishing_window: FishingWindowWidget, sea_temp: SeaTempWidget,
  whale_season: WhaleSeasonWidget,
  trip_planner: TripPlannerWidget, currency: CurrencyWidget,
  drive_time: DriveTimeWidget, holidays: HolidaysWidget,
  return_countdown: ReturnCountdownWidget,
  solar_vitals: SolarVitalsWidget, solar_excess: SolarExcessWidget,
  precool: PrecoolWidget, property_mode: PropertyModeWidget,
  consumption_yoy: ConsumptionYoYWidget,
  hoa_newsletter: NewsletterWidget, news: NewsWidget,
  reservations: ReservationsWidget, quicklinks: QuickLinksWidget,
  property_tax: PropertyTaxWidget, baja_races: BajaRacesWidget,
};

const VIRTUAL_RENDERERS = {
  _events: EventsWidget,
};

export default function RotationMode({ onExit }) {
  const [rotation, setRotation] = useState(null);
  const [widgets, setWidgets] = useState({});
  const [tzOffsetMinutes, setTzOffsetMinutes] = useState(null);
  const [index, setIndex] = useState(0);
  const [progress, setProgress] = useState(0);
  const [paused, setPaused] = useState(false);
  const [err, setErr] = useState("");

  // Fetch config + widget list + settings once, then poll widget data
  // in the background so what's on screen stays live.
  const load = useCallback(async () => {
    try {
      const [rot, wl, settings] = await Promise.all([
        api.getRotation(),
        api.listWidgets(),
        api.settings(),
      ]);
      setRotation(rot.config);
      const byId = {};
      for (const w of wl.widgets || []) byId[w.id] = w;
      setWidgets(byId);
      setTzOffsetMinutes(settings.tz_offset_minutes ?? null);
      setErr("");
    } catch (ex) {
      setErr(ex.message || "load failed");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  // Effective sequence — filter out entries whose widget isn't loaded.
  const sequence = useMemo(() => {
    if (!rotation) return [];
    return (rotation.sequence || []).filter(
      (it) => it && it.widget_id && (widgets[it.widget_id] || VIRTUAL_RENDERERS[it.widget_id]),
    );
  }, [rotation, widgets]);

  const current = sequence[index] || sequence[0];
  const dwell = current?.dwell_seconds || rotation?.default_dwell_seconds || 20;

  // Progress + advance timer — tick every 250 ms so the progress bar
  // is smooth.
  useEffect(() => {
    if (!sequence.length || paused) return;
    setProgress(0);
    const start = Date.now();
    const tick = setInterval(() => {
      const pct = Math.min(1, (Date.now() - start) / (dwell * 1000));
      setProgress(pct);
      if (pct >= 1) {
        setIndex((i) => (i + 1) % sequence.length);
      }
    }, 250);
    return () => clearInterval(tick);
  }, [index, sequence, dwell, paused]);

  // Exit on Esc; space toggles pause
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") { onExit?.(); }
      else if (e.key === " ") { e.preventDefault(); setPaused((p) => !p); }
      else if (e.key === "ArrowRight") { setIndex((i) => (i + 1) % Math.max(1, sequence.length)); }
      else if (e.key === "ArrowLeft") { setIndex((i) => (i - 1 + Math.max(1, sequence.length)) % Math.max(1, sequence.length)); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onExit, sequence.length]);

  if (err) return <div className="rot-error">{err} <button onClick={onExit}>Exit</button></div>;
  if (!rotation) return <div className="rot-loading">Loading…</div>;
  if (sequence.length === 0) {
    return (
      <div className="rot-empty">
        <div>
          Rotation sequence is empty (or no known widgets in it).
          <br />Configure it in Lists → Rotation.
        </div>
        <button onClick={onExit}>Exit</button>
      </div>
    );
  }

  const widget = widgets[current.widget_id];
  const isVirtual = !!VIRTUAL_RENDERERS[current.widget_id];
  const Renderer = isVirtual
    ? VIRTUAL_RENDERERS[current.widget_id]
    : RENDERERS[widget?.meta?.kind];
  const title = isVirtual
    ? current.widget_id.replace(/^_/, "").replace(/_/g, " ").toUpperCase()
    : widget?.meta?.name || current.widget_id;

  return (
    <div className="rot-app" onClick={onExit} title="Click / Esc to exit">
      <div className="rot-header">
        <div className="rot-title">{title}</div>
        <div className="rot-meta">
          <span>{index + 1} / {sequence.length}</span>
          <span>· {dwell}s</span>
          {paused && <span className="rot-paused">· PAUSED</span>}
          <button
            className="rot-btn"
            onClick={(e) => { e.stopPropagation(); onExit?.(); }}
            title="Exit rotation (Esc)"
          >✕</button>
        </div>
      </div>
      <div
        className="rot-stage"
        onClick={(e) => e.stopPropagation()}
        onDoubleClick={onExit}
      >
        {Renderer ? (
          isVirtual ? (
            <Renderer />
          ) : (
            <Renderer
              data={widget?.data}
              tzOffsetMinutes={tzOffsetMinutes}
            />
          )
        ) : (
          <div className="muted">No renderer for {current.widget_id}</div>
        )}
      </div>
      <div
        className="rot-progress"
        style={{ width: `${progress * 100}%` }}
      />
      <div className="rot-hint">
        ← → to navigate · space to pause · Esc / click to exit
      </div>
    </div>
  );
}
