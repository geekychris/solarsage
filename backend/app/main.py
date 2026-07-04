"""FastAPI app exposing EG4 Monitor data + history to the React UI."""

from __future__ import annotations

import asyncio
import logging
import aiohttp
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from eg4_inverter_api import EG4InverterAPI
from eg4_inverter_api.exceptions import EG4APIError, EG4AuthError
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from datetime import datetime, timedelta, timezone
import json

import aiosqlite

from . import credentials as creds_store
from . import weather as weather_api
from .ac_model import fit_ac_model
from .alerts_watcher import run_alerts
from .network_watcher import run_network_watcher
from .rollup import run_rollup, run_rollup_for_day
from .appliances_catalog import seed_for_site
from .eg4_history import EG4ChartError, fetch_day_attr, fetch_day_multiline
from .scheduler import schedule_appliances
from .forecast import (
    LocationConfig,
    battery_completion,
    excess_today,
    max_production_envelope,
    solar_today,
)
from .poller import run_poller
from .schemas import LoginRequest, LoginResponse
from .session_store import Session, SessionStore
from .storage import History
from .widgets import WidgetStore, registry as widget_registry, run_widget_refreshers
from .widgets.base import Widget
from .widgets.refresher import refresh_now as widget_refresh_now
from .widgets.tide import TideWidget
from .widgets.border import BorderWidget
from .widgets.hoa import HoaWidget
from .widgets.safety_quakes import QuakesWidget
from .widgets.safety_storms import StormsWidget
from .widgets.safety_uv import UvHeatWidget
from .widgets.outdoor_marine import MarineWidget
from .widgets.outdoor_sunmoon import SunMoonWidget
from .widgets.travel_currency import CurrencyWidget
from .widgets.travel_drive import DriveTimeWidget
from .widgets.travel_holidays import HolidaysWidget
from .widgets.solar_excess import SolarExcessWidget
from .widgets.solar_precool import PrecoolWidget
from .widgets.community_newsletter import NewsletterWidget
from .widgets.weather import WeatherWidget
from .widgets.safety_aqi import AqiWidget
from .widgets.quicklinks import QuickLinksWidget
from .widgets.water_tank import WaterTankWidget
from .widgets.sunset import SunsetWidget
from .widgets.acpv_overlay import AcPvOverlayWidget
from .widgets.when_to_run import WhenToRunWidget
from .widgets.climate_chart import ClimateChartWidget
from .widgets.peak_load import PeakLoadWidget
from .widgets.forecast_accuracy import ForecastAccuracyWidget
from .widgets.sky_tonight import SkyTonightWidget
from .widgets.meteor_showers import MeteorShowersWidget
from .widgets.bird_migration import BirdMigrationWidget
from .widgets.dab_pump import DabPumpWidget
from .widgets.dab_pump_control import DabPumpControlWidget
from .widgets.dab_pump_history import DabPumpHistoryWidget
from .widgets.property_mode import PropertyModeWidget
from .widgets.news import NewsWidget
from .widgets.reservations import ReservationsWidget
from .widgets.outdoor_fishing import FishingWindowWidget
from .widgets.trip_planner import TripPlannerWidget
from .widgets.property_tax import PropertyTaxWidget
from .widgets.return_countdown import ReturnCountdownWidget
from .widgets.whale_season import WhaleSeasonWidget
from .widgets.sea_temp import SeaTempWidget
from .widgets.baja_news import BajaNewsWidget
from .widgets.baja_races import BajaRacesWidget
from .widgets.contacts import ContactsWidget
from .widgets.shopping_list import ShoppingListWidget
from .widgets.border_log import BorderLogWidget
from .widgets.spanish import SpanishWidget
from .widgets.costco_fuel import CostcoFuelWidget
from .widgets.consumption_yoy import ConsumptionYoYWidget
from .widgets.solar_vitals import SolarVitalsWidget
from .widgets.ac_override import AcOverrideWidget
from .widgets.smart_ac_decisions import SmartAcDecisionsWidget
from .translations import TranslationsStore, mymemory_translate
from .widgets.todo import TodoWidget
from .sheets import SheetsSync, load_sheets_from_env
from .news_store import NewsStore
from .events import EventStore, run_reminder_scheduler
from .events.store import Event as EventRow, Reminder as ReminderRow, event_to_dict
from .events.scheduler import _ingest_once as events_ingest_once
from .events.tts import say as tts_say
from .subscriptions import (
    SubscriptionStore,
    evaluate_and_fire as _sub_evaluate_and_fire,
)
from . import notify as _notify
from .mqtt_publisher import MqttPublisher, load_from_env as _load_mqtt

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("eg4.api")

BASE_URL = os.getenv("EG4_BASE_URL", "https://monitor.eg4electronics.com")
DB_PATH = os.getenv("EG4_DB_PATH", "./eg4_history.db")
POLL_INTERVAL = int(os.getenv("EG4_POLL_INTERVAL", "60"))
IGNORE_SSL = os.getenv("EG4_DISABLE_VERIFY_SSL", "0") == "1"
API_KEY = os.getenv("EG4_API_KEY") or None
AUTO_USERNAME = os.getenv("EG4_USERNAME") or None
AUTO_PASSWORD = os.getenv("EG4_PASSWORD") or None

sessions = SessionStore()
history = History(DB_PATH)
widget_store = WidgetStore(DB_PATH)
event_store = EventStore(DB_PATH)
translations_store = TranslationsStore(DB_PATH)
news_store = NewsStore(DB_PATH)
subscriptions_store = SubscriptionStore(DB_PATH)
sheets: SheetsSync | None = load_sheets_from_env()
if sheets is not None:
    log.info("Google Sheets sync enabled")
else:
    log.info("Google Sheets sync not configured (widgets use SQLite)")
mqtt: MqttPublisher | None = _load_mqtt()
if mqtt is not None:
    log.info("MQTT publishing enabled (broker=%s)", mqtt.broker)
else:
    log.info("MQTT publishing not configured")
_SUBS_BUNDLE = {
    "store": subscriptions_store,
    "evaluate_and_fire": _sub_evaluate_and_fire,
}


def _register_builtin_widgets() -> None:
    """One place to wire up the shipped widgets. Adding a new widget = add
    a class + register it here; nothing else in main.py needs to change."""
    # Idempotent: register on app import, but skip dupes so reload-in-place
    # during dev doesn't crash.
    for widget in (
        TideWidget(),
        HoaWidget(),
        BorderWidget(),
        # Safety
        QuakesWidget(),
        StormsWidget(),
        UvHeatWidget(),
        AqiWidget(),
        # Outdoor
        WeatherWidget(),
        MarineWidget(),
        SunMoonWidget(),
        FishingWindowWidget(),
        # Outdoor extras
        SeaTempWidget(),
        WhaleSeasonWidget(),
        # Travel
        TripPlannerWidget(),
        ReturnCountdownWidget(),
        CurrencyWidget(),
        CostcoFuelWidget(),
        DriveTimeWidget(),
        HolidaysWidget(),
        BorderLogWidget(),
        ShoppingListWidget(),
        # Solar synergy
        PropertyModeWidget(),
        SolarVitalsWidget(),
        AcOverrideWidget(),
        SmartAcDecisionsWidget(),
        SolarExcessWidget(),
        PrecoolWidget(),
        ConsumptionYoYWidget(),
        # Community
        NewsletterWidget(),
        NewsWidget(),
        BajaNewsWidget(),
        BajaRacesWidget(),
        ReservationsWidget(),
        QuickLinksWidget(),
        WaterTankWidget(),
        SunsetWidget(),
        AcPvOverlayWidget(),
        WhenToRunWidget(),
        ClimateChartWidget(),
        PeakLoadWidget(),
        ForecastAccuracyWidget(),
        SkyTonightWidget(),
        MeteorShowersWidget(),
        BirdMigrationWidget(),
        DabPumpWidget(),
        DabPumpControlWidget(),
        DabPumpHistoryWidget(),
        PropertyTaxWidget(),
        ContactsWidget(),
        TodoWidget(),
        SpanishWidget(),
    ):
        if widget_registry.get(widget.id) is None:
            widget_registry.register(widget)


_register_builtin_widgets()


def _resolve_auto_credentials() -> tuple[str, str] | None:
    """Saved-file takes precedence over .env. None if neither is configured."""
    file_creds = creds_store.load()
    if file_creds:
        return file_creds
    if AUTO_USERNAME and AUTO_PASSWORD:
        return (AUTO_USERNAME, AUTO_PASSWORD)
    return None


async def _auto_login_loop() -> None:
    """Keep a backend session alive forever if creds are available.

    Re-establishes the EG4 client + poller on auth failures or transient errors.
    Runs in the background — never blocks startup. Re-reads the file each
    iteration so the user can save creds without restarting the server.
    """
    while True:
        creds = _resolve_auto_credentials()
        if creds is None:
            await asyncio.sleep(30)
            continue
        username, password = creds
        try:
            client = EG4InverterAPI(username=username, password=password, base_url=BASE_URL)
            await client.login(ignore_ssl=IGNORE_SSL)
            session = await sessions.create_persisted(username, client)
            log.info("auto-login OK for %s (token=%s…)", username, session.token[:8])
            session.poller_task = asyncio.create_task(
                run_poller(session, history, POLL_INTERVAL)
            )
            try:
                await session.poller_task
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("auto-login poller crashed; will restart in 30s")
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("auto-login attempt failed; retrying in 30s")
        await asyncio.sleep(30)


async def _bootstrap_default_site() -> None:
    """If the user has only a default EG4 setup (creds + the legacy settings
    row), make sure a 'site-1' row exists in the sites table so the new
    multi-site UI has something to show."""
    existing = await history.list_sites()
    if existing:
        return
    saved = creds_store.load()
    if not saved:
        return
    settings = await _load_settings()
    site = {
        "id": "site-1",
        "name": "Home",
        "vendor": "eg4",
        "lat": float(settings.get("lat", 31.025)),
        "lon": float(settings.get("lon", -114.838)),
        "tz": str(settings.get("tz", "America/Tijuana")),
        "peak_kw": float(settings.get("peak_kw", 10.0)),
        "battery_capacity_kwh": float(settings.get("battery_capacity_kwh", 14.3)),
        "max_charge_kw": float(settings.get("max_charge_kw", 8.0)),
        "config_json": {},
        "credentials_json": {"username": saved[0], "password": saved[1]},
    }
    await history.upsert_site(site)
    log.info("created default site-1 from saved EG4 credentials")
    # seed appliance catalog
    for a in seed_for_site("site-1"):
        await history.upsert_appliance(a)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    await history.init()
    # Give the session store a reference so login tokens survive restarts.
    sessions.bind_history(history)
    # Overlay any DB-backed integration settings on top of the env vars.
    await _refresh_integration_cache()
    await widget_store.init()
    await event_store.init()
    await translations_store.init()
    await news_store.init()
    await subscriptions_store.init()
    await _bootstrap_default_site()
    log.info("history db ready at %s", DB_PATH)
    # Start the auto-login loop unconditionally — it idles if no creds are
    # configured and picks them up the moment the user clicks "Save" in the UI.
    auto_task = asyncio.create_task(_auto_login_loop())
    log.info("auto-login background task started")
    alerts_task = asyncio.create_task(run_alerts(history))
    log.info("alerts watcher started")
    network_task = asyncio.create_task(run_network_watcher(history))
    log.info("network watcher started")
    rollup_task = asyncio.create_task(run_rollup(history, sheets, DB_PATH))
    log.info("rollup task started")
    if sheets is not None:
        # Materialize any Sheets-backed widget tabs that don't exist yet.
        for _w in widget_registry.all():
            if _w.sheets_tab and _w.sheets_field_order:
                try:
                    await sheets.ensure_tab(_w.sheets_tab, _w.sheets_field_order)
                except Exception as exc:  # noqa: BLE001
                    log.warning(
                        "sheets: could not ensure tab %r for %s: %s",
                        _w.sheets_tab, _w.id, exc,
                    )
    widgets_task = asyncio.create_task(
        run_widget_refreshers(
            widget_registry, widget_store, sheets, _SUBS_BUNDLE, mqtt,
        )
    )
    log.info(
        "widget refreshers started (%d widgets, subs=on, mqtt=%s)",
        len(list(widget_registry.all())), "on" if mqtt else "off",
    )
    events_task = asyncio.create_task(
        run_reminder_scheduler(event_store, widget_store, history_store=history)
    )
    log.info("event reminder scheduler started")
    yield
    events_task.cancel()
    widgets_task.cancel()
    alerts_task.cancel()
    network_task.cancel()
    rollup_task.cancel()
    if auto_task:
        auto_task.cancel()
    if mqtt is not None:
        await mqtt.close()
    await sessions.drop_all()


app = FastAPI(
    title="SolarSage",
    description=(
        "Monitor · Predict · Optimize — EG4 solar telemetry, history, "
        "weather-aware forecasts, plus introspectable dashboard widgets "
        "(tides, border wait times, HOA activities) and a TTS-driven "
        "reminder service.\n\n"
        "Auth: send `X-API-Key: <key>` (configured via `EG4_API_KEY` "
        "env var) for read-only endpoints, or `Authorization: Bearer "
        "<token>` from `/api/login` for endpoints that need a live EG4 "
        "session.\n\n"
        "Home-automation integration: poll `/api/widgets` for all "
        "knowledge-store payloads, `/api/events/today` for today's "
        "schedule, and POST to `/api/tts/say` to speak arbitrary text."
    ),
    openapi_tags=[
        {"name": "widgets", "description": "Self-describing dashboard "
         "widgets (tides, border wait times, HOA activities). Each widget "
         "publishes its own metadata + cached data."},
        {"name": "events", "description": "Scheduled events + reminders. "
         "Events come from the HOA weekly PDF (auto) or manual POSTs. "
         "Reminders fire via the Pi's local TTS service."},
        {"name": "tts", "description": "Local text-to-speech passthrough."},
    ],
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local-only app — see README
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _resolve_auth(
    authorization: str | None,
    x_api_key: str | None,
    api_key_q: str | None,
) -> tuple[Session | None, bool]:
    """Returns (session_or_None, is_api_key_auth). Raises 401 on no auth."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        # Falls back to the persisted token→username table so that a
        # browser's stored token continues to work after a backend
        # restart — the returned Session is whichever live session
        # currently belongs to that username (auto-login's usually).
        s = await sessions.get_or_restore(token)
        if s is not None:
            return s, False
    presented = x_api_key or api_key_q
    if API_KEY and presented and presented == API_KEY:
        latest = max(sessions._sessions.values(), key=lambda s: s.created_at, default=None)
        return latest, True
    raise HTTPException(status_code=401, detail="missing or invalid auth")


async def require_session(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Query(default=None, alias="api_key"),
) -> Session:
    """For endpoints that talk to EG4: a live session must exist."""
    s, is_key = await _resolve_auth(authorization, x_api_key, api_key)
    if s is None:
        raise HTTPException(
            status_code=412,
            detail="API key valid, but no EG4 session is active. Sign in via the UI first.",
        )
    return s


async def require_read(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Query(default=None, alias="api_key"),
) -> Session | None:
    """For SQL-only read endpoints: API key works even without an active session."""
    s, _ = await _resolve_auth(authorization, x_api_key, api_key)
    return s


async def read_or_public(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Query(default=None, alias="api_key"),
) -> Session | None:
    """Like ``require_read`` but silently returns ``None`` for
    unauthenticated readers instead of raising 401. Use for
    non-sensitive read endpoints the widget dashboard needs when
    the user hasn't signed into EG4 yet."""
    try:
        s, _ = await _resolve_auth(authorization, x_api_key, api_key)
        return s
    except HTTPException:
        return None


def _inverter_to_dict(inv: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in inv.__dict__.items():
        if k.startswith("_"):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
    return out


@app.post("/api/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    client = EG4InverterAPI(username=req.username, password=req.password, base_url=BASE_URL)
    try:
        await client.login(ignore_ssl=IGNORE_SSL)
    except EG4AuthError as exc:
        await client.close()
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except EG4APIError as exc:
        await client.close()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # aiohttp transport / TLS / DNS errors
        await client.close()
        msg = str(exc) or exc.__class__.__name__
        if "certificate" in msg.lower() or "ssl" in msg.lower():
            msg = (
                f"TLS error reaching {BASE_URL}: {msg}. "
                "If you trust your network, set EG4_DISABLE_VERIFY_SSL=1 in backend/.env and restart."
            )
        raise HTTPException(status_code=502, detail=msg) from exc

    session = await sessions.create_persisted(req.username, client)
    # kick off the historical poller for this session
    session.poller_task = asyncio.create_task(
        run_poller(session, history, POLL_INTERVAL)
    )

    remembered = False
    if req.remember:
        try:
            creds_store.save(req.username, req.password)
            remembered = True
            log.info("creds saved to %s for %s", os.getenv("EG4_CREDS_PATH", "./credentials.json"), req.username)
        except Exception as exc:
            log.warning("could not persist creds: %s", exc)

    return LoginResponse(
        token=session.token,
        username=req.username,
        inverter_count=len(client.get_inverters()),
        remembered=remembered,
    )


@app.post("/api/logout")
async def logout(
    forget: bool = Query(default=False),
    session: Session = Depends(require_session),
):
    await sessions.drop(session.token)
    forgotten = creds_store.clear() if forget else False
    return {"ok": True, "credentials_forgotten": forgotten}


@app.get("/api/auth/status")
async def auth_status():
    """Public — tells the login screen whether creds are already remembered."""
    return {
        "credentials_persisted": creds_store.exists(),
        "active_sessions": len(sessions._sessions),
    }


@app.post("/api/auth/use_saved")
async def use_saved():
    """Hand the caller a token for the auto-login session.

    Returns the token of the most recent session whose username matches the
    saved credentials. No additional auth required because the backend only
    listens on 127.0.0.1 (see `--host` in the run command). The caller proves
    they're entitled to this token by being on localhost.
    """
    saved = creds_store.load()
    if not saved:
        raise HTTPException(status_code=404, detail="no saved credentials")
    username, _ = saved
    matching = [s for s in sessions._sessions.values() if s.username == username]
    if not matching:
        raise HTTPException(
            status_code=503,
            detail="saved credentials present but auto-login session not ready yet",
        )
    s = max(matching, key=lambda s: s.created_at)
    return {"token": s.token, "username": s.username, "inverter_count": len(s.client.get_inverters())}


@app.get("/api/inverters")
async def list_inverters(session: Session = Depends(require_session)):
    return {
        "username": session.username,
        "inverters": [_inverter_to_dict(i) for i in session.client.get_inverters()],
    }


async def _fetch(session: Session, serial: str, method: str) -> dict[str, Any]:
    async with session.lock:
        session.client.set_selected_inverter(serialNum=serial)
        result = await getattr(session.client, method)()
    if not hasattr(result, "to_dict"):
        raise HTTPException(status_code=502, detail=f"EG4 returned error: {result!r}")
    return result.to_dict()


@app.get("/api/runtime")
async def runtime(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    data = await _fetch(session, serial, "get_inverter_runtime_async")
    return {"serial": serial, "ts": int(time.time() * 1000), "data": data}


@app.get("/api/energy")
async def energy(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    data = await _fetch(session, serial, "get_inverter_energy_async")
    return {"serial": serial, "ts": int(time.time() * 1000), "data": data}


@app.get("/api/battery")
async def battery(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    data = await _fetch(session, serial, "get_inverter_battery_async")
    return {"serial": serial, "ts": int(time.time() * 1000), "data": data}


@app.get("/api/snapshot")
async def snapshot(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    """Convenience endpoint: runtime+energy+battery in one call."""
    r = await _fetch(session, serial, "get_inverter_runtime_async")
    e = await _fetch(session, serial, "get_inverter_energy_async")
    b = await _fetch(session, serial, "get_inverter_battery_async")
    return {
        "serial": serial,
        "ts": int(time.time() * 1000),
        "runtime": r,
        "energy": e,
        "battery": b,
    }


@app.get("/api/metrics")
async def metrics(
    serial: str = Query(..., alias="serial"),
    session: Session | None = Depends(require_read),
):
    """List of (category, field) pairs the history DB has for this inverter."""
    fields = await history.list_fields(serial)
    return {"serial": serial, "metrics": fields}


@app.get("/api/history")
async def history_query(
    serial: str = Query(..., alias="serial"),
    field: str = Query(..., alias="field"),
    start: int | None = Query(default=None, description="unix ms"),
    end: int | None = Query(default=None, description="unix ms"),
    range_minutes: int | None = Query(default=None, alias="range_minutes"),
    max_points: int = Query(default=1000, ge=10, le=5000),
    session: Session | None = Depends(require_read),
):
    now = int(time.time() * 1000)
    if end is None:
        end = now
    if start is None:
        minutes = range_minutes if range_minutes is not None else 60
        start = end - minutes * 60_000
    points = await history.query(serial, field, start, end, max_points=max_points)
    return {
        "serial": serial,
        "field": field,
        "start": start,
        "end": end,
        "points": points,
    }


DEFAULT_SETTINGS = {
    # San Felipe, Baja California, Mexico
    "lat": 31.025,
    "lon": -114.838,
    "tz": "America/Tijuana",
    "peak_kw": 10.0,
    "battery_capacity_kwh": 14.3,
    "max_charge_kw": 8.0,
    "history_days": 7,
    # Integrations — URL/tokens for services SolarSage talks to. These
    # were env-vars-only; now they live in the settings table so the
    # UI can edit them. Env still wins if the DB value is empty.
    "ha_url": "",
    "ha_token": "",
    "tts_url": "",
    "notify_telegram_service": "",
    "notify_telegram_target": "",
    "worldtides_api_key": "",
    "eia_api_key": "",
    # Display-name overrides for widget tabs. Keys are internal tab
    # names (a widget's ``default_tab`` or its persisted ``_tab``);
    # values are the label the UI shows. Two internal names mapping
    # to the same label merge into one visible tab.
    #   {"Solar": "House", "Local": "House", "Community": "Home & HOA"}
    "tab_labels": {},
}


# Global cache for DB-backed integration settings — refreshed on save so
# hot-path calls (widget refreshers, notify dispatch, /api/smart_ac/override)
# don't hit SQLite every request.
_INTEGRATION_CACHE: dict[str, str] = {}


async def _refresh_integration_cache() -> None:
    """Reload DB integration settings into the process-level cache and
    export any populated ones as env vars so downstream code that reads
    ``os.getenv(...)`` picks up the new value without changes."""
    raw = await history.get_settings()
    global _INTEGRATION_CACHE
    _INTEGRATION_CACHE = {}
    for k in (
        "ha_url", "ha_token", "tts_url",
        "notify_telegram_service", "notify_telegram_target",
        "worldtides_api_key", "eia_api_key",
    ):
        v = raw.get(k)
        try:
            v = json.loads(v) if v is not None else ""
        except Exception:  # noqa: BLE001
            pass
        if isinstance(v, str) and v:
            _INTEGRATION_CACHE[k] = v
            # Mirror to env so os.getenv() sites transparently pick up
            # settings edits without a redeploy. Uppercase env-var
            # convention matches what the codebase already reads.
            os.environ[k.upper()] = v
    # Mirror global location too — widgets that need lat/lon and don't
    # have widget-config overrides can consult SOLARSAGE_LAT / _LON.
    for k in ("lat", "lon"):
        v = raw.get(k)
        try:
            v = json.loads(v) if v is not None else None
        except Exception:  # noqa: BLE001
            pass
        if isinstance(v, (int, float, str)):
            os.environ[f"SOLARSAGE_{k.upper()}"] = str(v)


def _tz_offset_minutes(tz_name: str) -> int:
    """Resolve an IANA tz name to current UTC offset minutes (DST-aware)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
        return int(datetime.now(tz).utcoffset().total_seconds() / 60)
    except Exception:
        # fall back: if user typed a numeric offset like "-420" or "-7"
        try:
            n = float(tz_name)
            return int(n if abs(n) > 16 else n * 60)
        except Exception:
            return -420  # PDT


async def _load_settings() -> dict:
    raw = await history.get_settings()
    out = dict(DEFAULT_SETTINGS)
    for k, v in raw.items():
        try:
            out[k] = json.loads(v)
        except Exception:
            out[k] = v
    return out


def _location_from(settings: dict) -> LocationConfig:
    return LocationConfig(
        lat=float(settings["lat"]),
        lon=float(settings["lon"]),
        tz_offset_minutes=_tz_offset_minutes(str(settings.get("tz", "America/Tijuana"))),
        peak_kw=float(settings["peak_kw"]),
        battery_capacity_kwh=float(settings["battery_capacity_kwh"]),
        max_charge_kw=float(settings["max_charge_kw"]),
    )


@app.get("/api/settings")
async def get_settings(session: Session = Depends(read_or_public)):
    s = await _load_settings()
    s["tz_offset_minutes"] = _tz_offset_minutes(str(s.get("tz", "America/Tijuana")))
    # Fall back to env vars for the integration secrets so the UI shows
    # whatever value is currently in use (DB wins; env is the fallback).
    # This is what makes the "reveal eye" work even before the user
    # saves to DB — the field shows what's really configured.
    integration_keys = (
        "ha_url", "ha_token", "tts_url",
        "notify_telegram_service", "notify_telegram_target",
        "worldtides_api_key", "eia_api_key",
    )
    for k in integration_keys:
        if not s.get(k):
            env_v = os.getenv(k.upper())
            if env_v:
                s[k] = env_v
    return s


@app.put("/api/settings")
async def put_settings(
    body: dict[str, Any],
    session: Session = Depends(require_session),
):
    allowed = set(DEFAULT_SETTINGS.keys())
    to_write = {k: json.dumps(v) for k, v in body.items() if k in allowed}
    if not to_write:
        raise HTTPException(status_code=400, detail="no recognized settings in body")
    await history.set_settings(to_write)
    # If any integration field moved, mirror to env so downstream
    # ``os.getenv`` sites (notify, HA calls, etc.) pick it up next
    # request without a restart.
    integration_keys = {
        "ha_url", "ha_token", "tts_url",
        "notify_telegram_service", "notify_telegram_target",
        "worldtides_api_key", "eia_api_key",
    }
    if any(k in integration_keys for k in to_write):
        await _refresh_integration_cache()
    return await _load_settings()


@app.get("/api/forecast/solar_today")
async def forecast_solar_today(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    settings = await _load_settings()
    loc = _location_from(settings)
    return await solar_today(
        history, serial, loc, hist_days=int(settings.get("history_days", 7))
    )


@app.get("/api/forecast/battery_completion")
async def forecast_battery_completion(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    settings = await _load_settings()
    loc = _location_from(settings)
    return await battery_completion(history, serial, loc)


@app.post("/api/debug/eg4")
async def debug_eg4(
    body: dict[str, Any],
    session: Session = Depends(require_session),
):
    """Raw passthrough to any EG4 portal endpoint using the active session.

    Body shape: {"path": "/WManage/api/...", "payload": "k=v&...", "method": "POST"}
    Returns the upstream HTTP status, content-type, body length, and first
    2 KB of the body — enough to diagnose endpoint-not-found vs auth vs
    response-shape mismatches without polluting the response with a huge dump.
    """
    path = body.get("path") or ""
    payload = body.get("payload") or ""
    method = (body.get("method") or "POST").upper()
    if not path.startswith("/"):
        raise HTTPException(status_code=400, detail="path must start with /")
    client = session.client
    upstream_session = await client._get_session()
    url = f"{client._base_url}{path}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
    }
    async with upstream_session.request(method, url, data=payload, headers=headers) as r:
        text = await r.text()
        ct = r.headers.get("Content-Type", "")
        sample = text[:16384]
        return {
            "url": url,
            "method": method,
            "request_payload": payload,
            "status": r.status,
            "content_type": ct,
            "length": len(text),
            "body_sample": sample,
        }


@app.get("/api/diagnostic")
async def diagnostic(
    serial: str = Query(..., alias="serial"),
    session: Session = Depends(require_session),
):
    """Return the exact field names + values EG4 is currently returning.

    Useful when live tiles show '—' — compare the keys here against the
    candidate lists in LiveTiles.jsx.
    """
    out: dict[str, Any] = {"serial": serial}
    async with session.lock:
        session.client.set_selected_inverter(serialNum=serial)
        try:
            r = await session.client.get_inverter_runtime_async()
            out["runtime"] = {
                "type": type(r).__name__,
                "fields": r.to_dict() if hasattr(r, "to_dict") else None,
            }
        except Exception as exc:
            out["runtime"] = {"error": str(exc)}
        try:
            e = await session.client.get_inverter_energy_async()
            out["energy"] = {
                "type": type(e).__name__,
                "fields": e.to_dict() if hasattr(e, "to_dict") else None,
            }
        except Exception as exc:
            out["energy"] = {"error": str(exc)}
        try:
            b = await session.client.get_inverter_battery_async()
            out["battery"] = {
                "type": type(b).__name__,
                "fields": b.to_dict() if hasattr(b, "to_dict") else None,
            }
        except Exception as exc:
            out["battery"] = {"error": str(exc)}
    # Stored history overview
    out["stored_fields"] = sorted(await history.known_fields(serial))
    settings = await _load_settings()
    out["coverage"] = await history.date_coverage(serial, _tz_offset_minutes(str(settings.get("tz", "America/Tijuana"))))
    return out


@app.post("/api/sync")
async def sync(
    serial: str = Query(..., alias="serial"),
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(require_session),
):
    """One-click historical pull + live snapshot capture.

    1. Pulls the last `days` days from EG4 via dayMultiLineParallel.
    2. Captures a live snapshot so the latest minute is in SQLite too.
    3. Reports what was written.
    """
    settings = await _load_settings()
    loc = _location_from(settings)
    tz_off = loc.tz_offset_minutes
    today_local = datetime.now(timezone.utc).astimezone(timezone(timedelta(minutes=tz_off))).date()
    day_results = []
    total_values = 0
    total_points = 0
    errors: list[str] = []

    async with session.lock:
        # Historical backfill
        for back in range(days - 1, -1, -1):
            d = today_local - timedelta(days=back)
            date_text = d.isoformat()
            try:
                samples = await fetch_day_multiline(session.client, serial, date_text, tz_off)
                tuples = [(s.ts_ms, s.fields) for s in samples]
                written = await history.upsert_many(serial, "historical", tuples)
                total_values += written
                total_points += len(samples)
                day_results.append({"date": date_text, "ok": True, "points": len(samples), "values": written})
            except EG4ChartError as exc:
                msg = f"{date_text}: HTTP {exc.status} from {exc.path}"
                errors.append(msg)
                day_results.append({
                    "date": date_text, "ok": False, "error": msg,
                    "upstream_status": exc.status,
                    "upstream_path": exc.path,
                    "upstream_content_type": exc.content_type,
                    "upstream_body_sample": exc.body_sample,
                })
            except Exception as exc:
                msg = f"{date_text}: {exc.__class__.__name__}: {exc}"
                errors.append(msg)
                day_results.append({"date": date_text, "ok": False, "error": msg})

        # Live snapshot — runs through the same poller pipeline so all numeric
        # fields land in the same SQLite store.
        try:
            session.client.set_selected_inverter(serialNum=serial)
            runtime = await session.client.get_inverter_runtime_async()
            energy = await session.client.get_inverter_energy_async()
            battery = await session.client.get_inverter_battery_async()
            if hasattr(runtime, "to_dict"):
                await history.record(serial, "runtime", runtime.to_dict())
            if hasattr(energy, "to_dict"):
                await history.record(serial, "energy", energy.to_dict())
            if hasattr(battery, "to_dict"):
                bd = battery.to_dict()
                await history.record(serial, "battery", {k: v for k, v in bd.items() if k != "battery_units"})
                for unit in bd.get("battery_units", []) or []:
                    idx = unit.get("batIndex")
                    if idx is None:
                        continue
                    await history.record(serial, "battery_unit", {
                        f"unit{idx}_soc": unit.get("soc"),
                        f"unit{idx}_soh": unit.get("soh"),
                        f"unit{idx}_voltage": unit.get("totalVoltage"),
                        f"unit{idx}_current": unit.get("current"),
                        f"unit{idx}_cycles": unit.get("cycleCnt"),
                    })
        except Exception as exc:
            errors.append(f"live snapshot: {exc}")

    days_with_data = sum(1 for d in day_results if d.get("ok") and d.get("points", 0) > 0)
    return {
        "serial": serial,
        "days_requested": days,
        "days_with_data": days_with_data,
        "total_points": total_points,
        "total_values_written": total_values,
        "stored_fields": sorted(await history.known_fields(serial)),
        "coverage": await history.date_coverage(serial, tz_off),
        "errors": errors,
        "days": day_results,
    }


@app.post("/api/backfill")
async def backfill(
    serial: str = Query(..., alias="serial"),
    days: int = Query(default=14, ge=1, le=365),
    overwrite: bool = Query(default=False),
    session: Session = Depends(require_session),
):
    """Pull `days` of historical chart data from EG4 into our SQLite store.

    Iterates from (today - days + 1) → today in the inverter's local timezone.
    Idempotent: re-running just updates existing rows.
    """
    settings = await _load_settings()
    loc = _location_from(settings)
    tz_off = loc.tz_offset_minutes
    today_local = datetime.now(timezone.utc).astimezone(timezone(timedelta(minutes=tz_off))).date()
    results = []
    total_samples = 0
    async with session.lock:
        for back in range(days - 1, -1, -1):
            d = today_local - timedelta(days=back)
            date_text = d.isoformat()
            try:
                samples = await fetch_day_multiline(session.client, serial, date_text, tz_off)
            except Exception as exc:
                log.exception("backfill day %s failed", date_text)
                results.append({"date": date_text, "ok": False, "error": str(exc)})
                continue
            tuples = [(s.ts_ms, s.fields) for s in samples]
            inserted = await history.upsert_many(serial, "historical", tuples)
            total_samples += inserted
            results.append({"date": date_text, "ok": True, "points": len(samples), "values": inserted})
    return {"serial": serial, "days_requested": days, "total_values_written": total_samples, "days": results}


@app.get("/api/coverage")
async def coverage(
    serial: str = Query(..., alias="serial"),
    session: Session | None = Depends(require_read),
):
    settings = await _load_settings()
    loc = _location_from(settings)
    return {
        "serial": serial,
        "tz_offset_minutes": loc.tz_offset_minutes,
        "by_date": await history.date_coverage(serial, loc.tz_offset_minutes),
    }


@app.get("/api/range")
async def range_query(
    serial: str = Query(..., alias="serial"),
    start: int | None = Query(default=None, description="UTC ms; omit with `days`/`end`"),
    end: int | None = Query(default=None, description="UTC ms; defaults to now"),
    days: float | None = Query(default=None, ge=0.04, le=3650, description="Convenience window from `end` backwards"),
    fields: str = Query(
        default="ppv,consumptionPower,pCharge,pDisCharge,pToGrid,pToUser,peps,soc",
        description="Comma-separated list of fields to return",
    ),
    target_points: int = Query(default=400, ge=20, le=5000, description="Approx points per series; controls bucket size"),
    session: Session | None = Depends(require_read),
):
    """Multi-channel time-range query for the UI charts.

    Auto-picks a bucket size based on (end-start)/target_points so panning across
    weeks doesn't return tens of thousands of points. Choices snap to
    {1m, 5m, 15m, 1h, 6h, 1d}."""
    now_ms = int(time.time() * 1000)
    if end is None:
        end = now_ms
    if start is None:
        if days is None:
            raise HTTPException(status_code=400, detail="provide either `start` or `days`")
        start = int(end - days * 86_400_000)
    if start >= end:
        raise HTTPException(status_code=400, detail="start must be < end")

    span_ms = end - start
    ideal_bucket_ms = max(60_000, span_ms // target_points)
    # Snap to a friendly bucket size
    SNAPS = [
        ("1m", 60_000),
        ("5m", 5 * 60_000),
        ("15m", 15 * 60_000),
        ("1h", 60 * 60_000),
        ("6h", 6 * 60 * 60_000),
        ("1d", 24 * 60 * 60_000),
    ]
    bucket_label, bucket_ms = SNAPS[0]
    for label, ms in SNAPS:
        if ms >= ideal_bucket_ms:
            bucket_label, bucket_ms = label, ms
            break
    else:
        bucket_label, bucket_ms = SNAPS[-1]

    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    series: dict[str, list[dict[str, float]]] = {}
    for f in field_list:
        # Bucketed AVG; ts returned is bucket start in UTC ms
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT (ts / ?) * ? AS bucket, AVG(value), COUNT(value)"
                " FROM samples"
                " WHERE serial_num = ? AND field = ? AND ts BETWEEN ? AND ?"
                " GROUP BY bucket ORDER BY bucket",
                (bucket_ms, bucket_ms, serial, f, start, end),
            )
            rows = await cur.fetchall()
        series[f] = [
            {"ts": int(b), "value": float(v), "count": int(c)}
            for b, v, c in rows
            if v is not None
        ]

    return {
        "serial": serial,
        "start_ms": start,
        "end_ms": end,
        "span_ms": span_ms,
        "bucket_ms": bucket_ms,
        "bucket_label": bucket_label,
        "fields": field_list,
        "series": series,
    }


@app.get("/api/daychart")
async def daychart(
    serial: str = Query(..., alias="serial"),
    date: str = Query(..., description="YYYY-MM-DD in inverter local tz"),
    fetch_if_missing: bool = Query(default=True),
    session: Session = Depends(require_session),
):
    """All channels for a specific local day, bucketed at 15 min for charting.

    Reads from SQLite first. If the day has no samples and `fetch_if_missing`
    is set, calls EG4's dayMultiLineParallel and caches the result before
    returning.
    """
    settings = await _load_settings()
    loc = _location_from(settings)
    tz_off = loc.tz_offset_minutes
    # local-day bounds in UTC ms
    y, mo, d = (int(x) for x in date.split("-"))
    day_start = datetime(y, mo, d, 0, 0, tzinfo=timezone(timedelta(minutes=tz_off)))
    day_end = day_start + timedelta(days=1)
    start_ms = int(day_start.astimezone(timezone.utc).timestamp() * 1000)
    end_ms = int(day_end.astimezone(timezone.utc).timestamp() * 1000)

    known = await history.known_fields(serial)
    fields_to_plot = [
        f for f in ("ppv", "consumptionPower", "pCharge", "pDisCharge", "gridPower", "soc", "acCouplePower")
        if f in known
    ]

    # If no samples yet for this day, try to backfill it just-in-time
    if fetch_if_missing:
        any_data = False
        for f in fields_to_plot or ["ppv"]:
            pts = await history.query(serial, f, start_ms, end_ms, max_points=2)
            if pts:
                any_data = True
                break
        if not any_data:
            async with session.lock:
                try:
                    samples = await fetch_day_multiline(session.client, serial, date, tz_off)
                    await history.upsert_many(serial, "historical", [(s.ts_ms, s.fields) for s in samples])
                    if samples:
                        known = await history.known_fields(serial)
                        fields_to_plot = [
                            f for f in ("ppv", "consumptionPower", "pCharge", "pDisCharge", "gridPower", "soc", "acCouplePower")
                            if f in known
                        ] or ["ppv"]
                except Exception as exc:
                    log.warning("just-in-time fetch for %s failed: %s", date, exc)

    series: dict[str, list[dict[str, float]]] = {}
    for f in fields_to_plot:
        series[f] = await history.query(serial, f, start_ms, end_ms, max_points=200)

    return {
        "serial": serial,
        "date": date,
        "tz_offset_minutes": tz_off,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "series": series,
    }


@app.get("/api/aggregate")
async def aggregate(
    serial: str = Query(..., alias="serial"),
    field: str = Query(..., description="Field name, e.g. ppv, consumptionPower, soc"),
    start: int | None = Query(default=None, description="UTC ms"),
    end: int | None = Query(default=None, description="UTC ms"),
    days: int | None = Query(default=None, ge=1, le=3650, description="Convenience: last N days"),
    group_by: str = Query(default="day", description="minute|hour|day|week|month|none"),
    fn: str = Query(default="avg", description="avg|sum|min|max|count"),
    session: Session | None = Depends(require_read),
):
    """Generic bucketed aggregation. Designed for analytic questions like
    'sum daily ppv for the last 30 days' or 'max hourly consumption over July'."""
    settings = await _load_settings()
    loc = _location_from(settings)
    now_ms = int(time.time() * 1000)
    if end is None:
        end = now_ms
    if start is None:
        if days is not None:
            start = end - days * 86_400_000
        else:
            start = end - 7 * 86_400_000
    try:
        rows = await history.aggregate(
            serial_num=serial, field=field, start_ms=start, end_ms=end,
            group_by=group_by, fn=fn, tz_offset_minutes=loc.tz_offset_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "serial": serial,
        "field": field,
        "start_ms": start,
        "end_ms": end,
        "group_by": group_by,
        "fn": fn,
        "tz_offset_minutes": loc.tz_offset_minutes,
        "rows": rows,
    }


def _power_to_kwh(rows: list[dict], sample_interval_min: float) -> dict[str, float]:
    """Approximate kWh by summing power × interval. Returns {bucket: kwh}."""
    out: dict[str, float] = {}
    for r in rows:
        if r["value"] is None:
            continue
        # value is avg W over the bucket; energy ≈ avg_W * (count * sample_min / 60) / 1000
        out[r["bucket"]] = r["value"] * (r["count"] * sample_interval_min / 60) / 1000
    return out


@app.get("/api/summary")
async def summary(
    serial: str = Query(..., alias="serial"),
    days: int = Query(default=30, ge=1, le=365),
    session: Session | None = Depends(require_read),
):
    """Single-call analytics summary: per-day kWh totals, all-time peaks, and
    a ranked list of best/worst days by solar production. Output is optimized
    for an LLM to read aloud and answer questions from."""
    settings = await _load_settings()
    loc = _location_from(settings)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86_400_000
    tz_off = loc.tz_offset_minutes

    known = await history.known_fields(serial)
    fields = {
        "solar_w": next((f for f in ("ppv", "solarPv", "pPV", "totalPv") if f in known), None),
        "load_w": next((f for f in ("consumptionPower", "consumption", "pLoad") if f in known), None),
        "charge_w": next((f for f in ("pCharge", "ppvpCharge", "batChargePower") if f in known), None),
        "discharge_w": next((f for f in ("pDisCharge", "batteryDischarging") if f in known), None),
        "grid_w": next((f for f in ("gridPower", "pToGrid") if f in known), None),
        "soc": next((f for f in ("soc", "unit0_soc", "batterySoc") if f in known), None),
    }

    # Daily kWh per metric (avg W per day × 24)
    daily: dict[str, list[dict]] = {}
    overall: dict[str, dict[str, float | None]] = {}
    for label, fname in fields.items():
        if not fname:
            daily[label] = []
            overall[label] = {"avg": None, "min": None, "max": None, "sum": None}
            continue
        daily_rows = await history.aggregate(
            serial, fname, start_ms, now_ms, group_by="day", fn="avg",
            tz_offset_minutes=tz_off,
        )
        # Convert average-W per day into approximate kWh: avg_W * 24 / 1000
        for r in daily_rows:
            if r["value"] is not None:
                r["kwh_estimate"] = r["value"] * 24 / 1000
        daily[label] = daily_rows
        overall[label] = await history.overall_stats(serial, fname, start_ms, now_ms)
        # convert overall avg W → kWh estimate over whole window (avg_W * hours_in_window / 1000)
        if overall[label]["avg"] is not None:
            hours = (now_ms - start_ms) / 3_600_000
            overall[label]["kwh_estimate"] = overall[label]["avg"] * hours / 1000

    # Best/worst solar days (only meaningful if we have solar field)
    best_days: list[dict] = []
    worst_days: list[dict] = []
    if fields["solar_w"]:
        solar_daily = sorted(
            [r for r in daily.get("solar_w", []) if r["value"] is not None],
            key=lambda r: r["value"], reverse=True,
        )
        best_days = solar_daily[:5]
        worst_days = solar_daily[-5:][::-1]

    return {
        "serial": serial,
        "days_window": days,
        "tz_offset_minutes": tz_off,
        "fields_used": fields,
        "daily": daily,
        "overall": overall,
        "best_solar_days": best_days,
        "worst_solar_days": worst_days,
    }


@app.get("/api/best_day")
async def best_day(
    serial: str = Query(..., alias="serial"),
    field: str = Query(default="ppv"),
    fn: str = Query(default="avg", description="avg|sum|max"),
    days: int = Query(default=365, ge=1, le=3650),
    direction: str = Query(default="best", description="best|worst"),
    n: int = Query(default=10, ge=1, le=100),
    session: Session | None = Depends(require_read),
):
    settings = await _load_settings()
    loc = _location_from(settings)
    now_ms = int(time.time() * 1000)
    rows = await history.aggregate(
        serial, field, now_ms - days * 86_400_000, now_ms,
        group_by="day", fn=fn, tz_offset_minutes=loc.tz_offset_minutes,
    )
    rows = [r for r in rows if r["value"] is not None]
    rows.sort(key=lambda r: r["value"], reverse=(direction == "best"))
    return {
        "serial": serial, "field": field, "fn": fn, "direction": direction,
        "rows": rows[:n],
    }


@app.get("/api/weather")
async def weather_endpoint(
    days: int = Query(default=7, ge=1, le=16),
    session: Session | None = Depends(require_read),
):
    settings = await _load_settings()
    try:
        f = await weather_api.forecast(
            lat=float(settings["lat"]),
            lon=float(settings["lon"]),
            days=days,
            tz=str(settings.get("tz", "auto")),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"open-meteo: {exc}") from exc
    return f


@app.get("/api/forecast/tomorrow")
async def forecast_tomorrow(
    serial: str = Query(..., alias="serial"),
    horizon_days: int = Query(default=2, ge=1, le=7, description="Forecast horizon (incl today)"),
    session: Session | None = Depends(require_read),
):
    """Hour-by-hour forecast of PV / base load / AC contribution / surplus.

    Combines: Open-Meteo solar irradiance & temperature forecast + a fitted
    cooling-degree AC model + the historical PV-vs-irradiance ratio observed
    for this system.
    """
    settings = await _load_settings()
    loc = _location_from(settings)
    tz = str(settings.get("tz", "auto"))

    # 1. Pull weather forecast (hourly)
    f = await weather_api.forecast(loc.lat, loc.lon, days=horizon_days, tz=tz)
    h = f.get("hourly") or {}
    times = h.get("time") or []
    temps = h.get("temperature_2m") or []
    ghi = h.get("shortwave_radiation") or []
    cloud = h.get("cloud_cover") or []
    if not times or len(times) != len(temps):
        raise HTTPException(status_code=502, detail="weather forecast missing hourly data")

    # 2. Fit AC model from the last 14 days of historical weather + load
    known = await history.known_fields(serial)
    load_field = next((f for f in ("consumptionPower", "peps") if f in known), None)
    ac_model = None
    if load_field:
        from datetime import date as _date
        today = _date.today()
        start_d = (today - timedelta(days=14)).isoformat()
        end_d = today.isoformat()
        try:
            arch = await weather_api.historical(loc.lat, loc.lon, start_d, end_d, tz=tz)
            ac_model = await fit_ac_model(
                history, serial, arch.get("hourly", {}),
                loc.tz_offset_minutes, load_field,
            )
        except Exception as exc:
            log.warning("ac_model fit failed: %s", exc)

    # 3. PV scaling: how much W per W/m² of GHI did this system produce on
    #    average historically (peak hours only, to avoid dawn/dusk noise).
    pv_field = next((f for f in ("ppv", "ppv1") if f in known), None)
    pv_per_ghi = None
    if pv_field:
        # Approximate by ratio of peak observed PV to peak GHI in archive
        pv_max_by_hour = await history.bucket_max_by_time_of_day(
            serial, pv_field, days=14, bucket_minutes=60,
            tz_offset_minutes=loc.tz_offset_minutes,
        )
        # Use the brightest historical hour as the calibration anchor; assume
        # clear-sky GHI ≈ 950 W/m² at solar noon for San Felipe in May
        peak_pv = max(pv_max_by_hour.values(), default=0.0)
        peak_ghi = max(ghi[:48] or [0])  # next 48 hours
        if peak_pv > 0 and peak_ghi > 0:
            pv_per_ghi = peak_pv / max(peak_ghi, 100)
        elif loc.peak_kw:
            # Fallback: kW per kW/m² at STC, derated 80% for real conditions
            pv_per_ghi = loc.peak_kw * 1000 * 0.8 / 1000  # W per W/m²

    # 4. Build per-hour forecast
    rows = []
    for i, t in enumerate(times):
        hour = int(t[11:13])
        temp_f = float(temps[i]) if temps[i] is not None else None
        cloud_pct = float(cloud[i]) if i < len(cloud) and cloud[i] is not None else None
        ghi_w = float(ghi[i]) if i < len(ghi) and ghi[i] is not None else 0.0

        # Predicted PV (W) — scale GHI by our system's PV-per-GHI ratio
        pred_pv = ghi_w * pv_per_ghi if pv_per_ghi else 0.0
        # Predicted load
        if ac_model and temp_f is not None:
            pred_load = ac_model.predict_load(hour, temp_f)
            ac_part = ac_model.slope_w_per_f * max(0.0, temp_f - ac_model.threshold_f)
            base_part = pred_load - ac_part
        else:
            pred_load = None
            ac_part = None
            base_part = None

        rows.append({
            "time": t,
            "hour_of_day": hour,
            "temperature_f": temp_f,
            "cloud_pct": cloud_pct,
            "ghi_wm2": ghi_w,
            "predicted_pv_w": pred_pv,
            "predicted_load_w": pred_load,
            "predicted_ac_w": ac_part,
            "predicted_base_load_w": base_part,
            "predicted_surplus_w": (
                pred_pv - pred_load if pred_load is not None else pred_pv
            ),
        })

    return {
        "serial": serial,
        "tz": tz,
        "location": {"lat": loc.lat, "lon": loc.lon},
        "ac_model": {
            "threshold_f": ac_model.threshold_f if ac_model else None,
            "slope_w_per_f": ac_model.slope_w_per_f if ac_model else None,
            "r_squared": ac_model.correlation if ac_model else None,
            "days_used": ac_model.days_used if ac_model else 0,
            "load_field": ac_model.load_field if ac_model else None,
        },
        "pv_calibration": {
            "field": pv_field,
            "w_per_ghi": pv_per_ghi,
        },
        "hourly": rows,
    }


@app.get("/api/forecast/excess")
async def forecast_excess(
    serial: str = Query(..., alias="serial"),
    session: Session | None = Depends(require_read),
):
    settings = await _load_settings()
    loc = _location_from(settings)
    return await excess_today(
        history, serial, loc, hist_days=int(settings.get("history_days", 14))
    )


@app.get("/api/forecast/max_production")
async def forecast_max_production(session: Session = Depends(require_session)):
    settings = await _load_settings()
    loc = _location_from(settings)
    return {
        "tz_offset_minutes": loc.tz_offset_minutes,
        "location": {"lat": loc.lat, "lon": loc.lon},
        "peak_kw": loc.peak_kw,
        "bucket_minutes": 15,
        "buckets": await max_production_envelope(loc),
    }


# ============================================================================
# Multi-site, appliances, scheduler, heatmap, alerts
# ============================================================================

@app.get("/api/sites")
async def list_sites(session: Session | None = Depends(require_read)):
    sites = await history.list_sites()
    # Redact credentials from the response
    for s in sites:
        s.pop("credentials_json", None)
    return {"sites": sites}


@app.post("/api/sites")
async def upsert_site(body: dict[str, Any], session: Session | None = Depends(require_read)):
    required = ("id", "name", "vendor", "lat", "lon", "tz")
    for k in required:
        if body.get(k) in (None, ""):
            raise HTTPException(status_code=400, detail=f"missing field: {k}")
    if body["vendor"] not in ("eg4", "solaredge", "qcell"):
        raise HTTPException(status_code=400, detail="vendor must be eg4|solaredge|qcell")
    await history.upsert_site(body)
    # Seed default appliances if this is a new site
    existing = await history.list_appliances(body["id"])
    if not existing:
        for a in seed_for_site(body["id"]):
            await history.upsert_appliance(a)
    return await history.get_site(body["id"])


@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: str, cascade: bool = Query(default=False),
                      session: Session | None = Depends(require_read)):
    await history.delete_site(site_id, cascade=cascade)
    return {"ok": True}


@app.get("/api/appliances")
async def list_appliances(site_id: str = Query(..., alias="site_id"),
                          session: Session | None = Depends(require_read)):
    return {"site_id": site_id, "appliances": await history.list_appliances(site_id)}


@app.post("/api/appliances")
async def upsert_appliance(body: dict[str, Any], session: Session | None = Depends(require_read)):
    if "site_id" not in body or "name" not in body or "watts" not in body:
        raise HTTPException(status_code=400, detail="site_id, name, watts required")
    body.setdefault("typical_minutes", 60)
    aid = await history.upsert_appliance(body)
    return {"id": aid}


@app.delete("/api/appliances/{appliance_id}")
async def delete_appliance(appliance_id: int, site_id: str = Query(...),
                           session: Session | None = Depends(require_read)):
    await history.delete_appliance(appliance_id, site_id)
    return {"ok": True}


@app.get("/api/schedule")
async def schedule(serial: str = Query(...), site_id: str = Query(default="site-1"),
                   session: Session | None = Depends(require_read)):
    """Smart-load-scheduler recommendations for enabled appliances at this site."""
    settings = await _load_settings()
    loc = _location_from(settings)
    appliances = await history.list_appliances(site_id)
    # Reuse the tomorrow forecast we already produce
    f = await weather_api.forecast(loc.lat, loc.lon, days=2, tz=str(settings.get("tz", "auto")))
    # We need the per-hour rows in the shape scheduler expects
    h = f.get("hourly") or {}
    rows = []
    for i, t in enumerate(h.get("time") or []):
        # Reuse the tomorrow endpoint's math here would be cleaner but for
        # now we approximate surplus from weather GHI alone — main.py's
        # forecast_tomorrow already does this for the UI.
        ghi = (h.get("shortwave_radiation") or [0])[i] or 0
        temp = (h.get("temperature_2m") or [0])[i]
        # Predicted PV via the same simple calibration (peak_kw * 0.8 cap)
        pred_pv = ghi * (loc.peak_kw * 0.8)  # W
        # Use historical-avg load curve for predicted load — fall back to 600
        pred_load = 600.0
        rows.append({"time": t, "predicted_surplus_w": pred_pv - pred_load,
                     "predicted_pv_w": pred_pv, "predicted_load_w": pred_load,
                     "temperature_f": temp})
    recs = schedule_appliances(appliances, rows, loc.tz_offset_minutes)
    return {"site_id": site_id, "recommendations": recs}


@app.get("/api/heatmap")
async def heatmap(serial: str = Query(...),
                  field: str = Query(default="ppv"),
                  days: int = Query(default=365, ge=7, le=3650),
                  session: Session | None = Depends(require_read)):
    """Daily aggregate (sum × avg-W → kWh-ish) for the calendar heatmap."""
    settings = await _load_settings()
    loc = _location_from(settings)
    now_ms = int(time.time() * 1000)
    rows = await history.aggregate(
        serial, field, now_ms - days * 86_400_000, now_ms,
        group_by="day", fn="avg", tz_offset_minutes=loc.tz_offset_minutes,
    )
    out = []
    for r in rows:
        if r["value"] is None:
            continue
        # convert avg W to approximate daily kWh (avg × 24h)
        out.append({"date": r["bucket"], "kwh": r["value"] * 24 / 1000, "samples": r["count"]})
    return {"serial": serial, "field": field, "days_window": days, "cells": out}


@app.get("/api/string_health")
async def string_health(serial: str = Query(...), days: int = Query(default=7),
                        session: Session | None = Depends(require_read)):
    """Per-string PV ratio over time. Catches one string drifting low."""
    settings = await _load_settings()
    loc = _location_from(settings)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86_400_000
    known = await history.known_fields(serial)
    strings = sorted([f for f in known if re.fullmatch(r"ppv[1-9]", f)])
    if not strings:
        return {"serial": serial, "strings": [], "note": "no per-string PV fields"}
    series: dict[str, list] = {}
    daily_totals: dict[str, dict[str, float]] = {}  # field -> {day: total}
    for s in strings:
        rows = await history.aggregate(
            serial, s, start_ms, now_ms, group_by="day", fn="avg",
            tz_offset_minutes=loc.tz_offset_minutes,
        )
        series[s] = [{"date": r["bucket"], "avg_w": r["value"]} for r in rows if r["value"] is not None]
    # Pairwise ratios over each day
    days_seen = sorted({d["date"] for s in series.values() for d in s})
    health: list[dict] = []
    for day in days_seen:
        by_s = {s: next((d["avg_w"] for d in series[s] if d["date"] == day), None) for s in strings}
        values = [v for v in by_s.values() if v]
        if not values:
            continue
        max_v = max(values)
        deviations = {s: ((by_s[s] or 0) / max_v if max_v else None) for s in strings}
        health.append({"date": day, "values": by_s, "ratio_to_strongest": deviations})
    return {"serial": serial, "strings": strings, "series": series, "health": health}


@app.get("/api/performance")
async def performance(serial: str = Query(...), days: int = Query(default=30),
                      session: Session | None = Depends(require_read)):
    """Actual daily PV kWh vs irradiance-expected daily kWh, for a degradation trend."""
    settings = await _load_settings()
    loc = _location_from(settings)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86_400_000
    pv_rows = await history.aggregate(
        serial, "ppv", start_ms, now_ms, group_by="day", fn="avg",
        tz_offset_minutes=loc.tz_offset_minutes,
    )
    # Pull historical irradiance for the same window
    from datetime import date as _date
    today = _date.today()
    start_d = (today - timedelta(days=days)).isoformat()
    end_d = today.isoformat()
    try:
        arch = await weather_api.historical(loc.lat, loc.lon, start_d, end_d, tz=str(settings.get("tz", "auto")))
    except Exception as exc:
        return {"serial": serial, "error": f"weather archive failed: {exc}"}
    hourly = arch.get("hourly") or {}
    ghi_daily: dict[str, float] = {}
    times = hourly.get("time") or []
    ghis = hourly.get("shortwave_radiation") or []
    for t, g in zip(times, ghis):
        if g is None:
            continue
        day = t[:10]
        ghi_daily[day] = ghi_daily.get(day, 0.0) + float(g)
    out = []
    for r in pv_rows:
        d = r["bucket"]
        actual = (r["value"] or 0) * 24 / 1000  # daily kWh estimate
        expected = ghi_daily.get(d, 0.0) * loc.peak_kw * 0.8 / 1000  # rough
        ratio = (actual / expected) if expected > 0 else None
        out.append({"date": d, "actual_kwh": actual, "expected_kwh": expected, "ratio": ratio})
    return {"serial": serial, "days": days, "rows": out}


@app.get("/api/export.csv")
async def export_csv(serial: str = Query(...), field: str = Query(default="ppv"),
                     start: int = Query(...), end: int = Query(...),
                     session: Session | None = Depends(require_read)):
    """Stream raw samples as CSV for any (field, range)."""
    points = await history.query(serial, field, start, end, max_points=100000)
    from fastapi.responses import Response
    lines = ["ts_ms,iso_utc,value"]
    for p in points:
        iso = datetime.fromtimestamp(p["ts"] / 1000, tz=timezone.utc).isoformat()
        lines.append(f"{p['ts']},{iso},{p['value']}")
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{serial}_{field}.csv"'})


@app.get("/api/alerts")
async def list_alerts(site_id: str = Query(default="site-1"),
                      limit: int = Query(default=50, ge=1, le=500),
                      unacknowledged_only: bool = Query(default=False),
                      session: Session | None = Depends(require_read)):
    return {"site_id": site_id, "alerts": await history.list_alerts(site_id, limit, unacknowledged_only)}


@app.post("/api/alerts/{alert_id}/ack")
async def ack_alert(alert_id: int, session: Session | None = Depends(require_read)):
    await history.acknowledge_alert(alert_id)
    return {"ok": True}


@app.get("/api/network/status")
async def network_status(session: Session | None = Depends(read_or_public)):
    """Current connectivity state: last probe, in-progress outage (if any),
    24h uptime %, and average round-trip latency."""
    now_ms = int(time.time() * 1000)
    day_ago = now_ms - 86_400_000
    latest = await history.latest_network_check()
    summary = await history.network_summary(day_ago)
    open_outage = await history.get_open_network_outage()
    uptime_pct = None
    if summary["total"]:
        uptime_pct = round(100.0 * summary["ok_count"] / summary["total"], 2)
    return {
        "now_ms": now_ms,
        "latest": latest,
        "open_outage": open_outage,
        "window_ms": 86_400_000,
        "summary": summary,
        "uptime_pct_24h": uptime_pct,
    }


@app.get("/api/network/history")
async def network_history(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=5000, ge=1, le=20000),
    session: Session | None = Depends(read_or_public),
):
    """Raw per-probe log for building timelines / charts."""
    since_ms = int(time.time() * 1000) - hours * 3_600_000
    return {
        "hours": hours,
        "since_ms": since_ms,
        "checks": await history.list_network_checks(since_ms, limit=limit),
    }


@app.get("/api/network/outages")
async def network_outages(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session | None = Depends(read_or_public),
):
    return {"outages": await history.list_network_outages(limit=limit)}


@app.post("/api/rollup/run")
async def rollup_run(
    date: str = Query(..., description="YYYY-MM-DD (inverter local tz)"),
    force: bool = Query(default=False, description="Re-append even if date already present"),
    session: Session = Depends(require_session),
):
    """Manually append one day's rollup rows to Google Sheets."""
    if sheets is None:
        raise HTTPException(status_code=412, detail="Google Sheets not configured")
    from datetime import date as _date_cls
    try:
        y, mo, d = (int(x) for x in date.split("-"))
        day = _date_cls(y, mo, d)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"bad date: {exc}") from exc
    return await run_rollup_for_day(
        history, sheets, DB_PATH, day, skip_if_exists=not force,
    )


def _analyze_day_cycle(
    soc_points: list[dict],
    day_start_ms: int,
    day_end_ms: int,
    capacity_kwh: float,
) -> dict | None:
    """Pull the day's drain/charge events out of a list of SoC samples.

    `soc_points` should cover [day_start_ms, day_start_ms + ~36h] sorted ASC.
    The drain cycle that *starts* in this calendar day is what gets reported —
    its trough and recovery may extend into the next day, which is why we want
    extra lookahead beyond `day_end_ms`.
    """
    if not soc_points or len(soc_points) < 5:
        return None

    values = [p["value"] for p in soc_points]
    ts = [p["ts"] for p in soc_points]

    # Peak SoC within the calendar day (this is "today is fully charged" point)
    in_day = [i for i, t in enumerate(ts) if day_start_ms <= t < day_end_ms]
    if not in_day:
        return None
    peak_idx = max(in_day, key=lambda i: values[i])
    # Use the LATEST index that's at the peak value — that's when drain begins
    peak_val = values[peak_idx]
    last_at_peak = max(
        (i for i in in_day if values[i] >= peak_val - 0.5),
        default=peak_idx,
    )

    # Trough: lowest SoC in the next 24h after the peak (may cross midnight)
    look_end = ts[last_at_peak] + 24 * 3_600_000
    after = [i for i in range(last_at_peak, len(values)) if ts[i] <= look_end]
    if len(after) < 2:
        # Not enough lookahead — fall back to within-day min
        min_idx = min(in_day, key=lambda i: values[i])
    else:
        min_idx = min(after, key=lambda i: values[i])

    min_val = values[min_idx]
    drop_pct = max(0.0, peak_val - min_val)

    drain_start_idx = None
    charge_start_idx = None
    full_idx = None

    if drop_pct >= 3 and min_idx > last_at_peak:
        # Drain start = latest sample at/near peak before the trough
        for i in range(min_idx - 1, last_at_peak - 1, -1):
            if values[i] >= peak_val - 1.5:
                drain_start_idx = i
                break
        if drain_start_idx is None:
            drain_start_idx = last_at_peak

        # Charge start = first sample after trough where SoC has risen by >=2%
        for i in range(min_idx + 1, len(values)):
            if values[i] >= min_val + 2:
                charge_start_idx = i
                break

        # Fully charged again = first sample at/near peak after charge start
        if charge_start_idx is not None:
            target = max(peak_val, 95) - 1
            for i in range(charge_start_idx, len(values)):
                if values[i] >= target:
                    full_idx = i
                    break

    def at(i: int | None) -> tuple[int | None, float | None]:
        if i is None:
            return None, None
        return int(ts[i]), float(values[i])

    peak_ts, _ = at(last_at_peak)
    min_ts, _ = at(min_idx)
    drain_ts, drain_soc = at(drain_start_idx)
    charge_ts, charge_soc = at(charge_start_idx)
    full_ts, full_val = at(full_idx)

    return {
        "peak_ts": peak_ts, "peak_soc": float(peak_val),
        "min_ts": min_ts, "min_soc": float(min_val),
        "drain_start_ts": drain_ts, "drain_start_soc": drain_soc,
        "charge_start_ts": charge_ts, "charge_start_soc": charge_soc,
        "full_charge_ts": full_ts, "full_charge_soc": full_val,
        "drain_pct": round(drop_pct, 1),
        "drain_kwh": round(drop_pct / 100.0 * capacity_kwh, 2),
        "samples": len(in_day),
    }


@app.get("/api/battery_cycles")
async def battery_cycles(
    serial: str = Query(..., alias="serial"),
    days: int = Query(default=14, ge=1, le=60),
    session: Session | None = Depends(require_read),
):
    """Per-day battery drain/charge events plus daily temperature range.

    Powers the "Battery vs temperature" panel — one row per local day with:
    - when the battery started draining (latest peak-SoC sample before the trough)
    - how far it drained (% and kWh, against the configured battery capacity)
    - when it started charging again (first significant SoC rise after the trough)
    - when it reached "full" (SoC back to peak / 95%+)
    - daily min / max / avg outdoor temperature in °F
    """
    settings = await _load_settings()
    loc = _location_from(settings)
    tz_off = loc.tz_offset_minutes
    capacity_kwh = float(loc.battery_capacity_kwh or 14.3)

    known = await history.known_fields(serial)
    soc_field = next((f for f in ("soc", "unit0_soc", "batterySoc") if f in known), None)
    if not soc_field:
        return {
            "serial": serial,
            "tz_offset_minutes": tz_off,
            "battery_capacity_kwh": capacity_kwh,
            "soc_field": None,
            "days": [],
            "note": "no SoC field in history",
        }

    today_local = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(minutes=tz_off))
    ).date()

    # Pull temps for the whole window in one Open-Meteo call. past_days covers
    # recent days (incl. today) that the archive endpoint doesn't have yet.
    temp_by_date: dict[str, dict[str, float]] = {}
    try:
        wx = await weather_api.forecast(
            loc.lat, loc.lon, days=1, tz=str(settings.get("tz", "auto")),
            past_days=days,
        )
        daily = wx.get("daily") or {}
        for d, tmin, tmax in zip(
            daily.get("time") or [],
            daily.get("temperature_2m_min") or [],
            daily.get("temperature_2m_max") or [],
        ):
            temp_by_date[d] = {
                "temp_min_f": float(tmin) if tmin is not None else None,
                "temp_max_f": float(tmax) if tmax is not None else None,
            }
        hourly = wx.get("hourly") or {}
        avg_acc: dict[str, list[float]] = {}
        for t, temp in zip(
            hourly.get("time") or [],
            hourly.get("temperature_2m") or [],
        ):
            if temp is None:
                continue
            d = t[:10]
            avg_acc.setdefault(d, []).append(float(temp))
        for d, vals in avg_acc.items():
            entry = temp_by_date.setdefault(d, {})
            entry["temp_avg_f"] = round(sum(vals) / len(vals), 1)
    except Exception as exc:
        log.warning("battery_cycles: weather lookup failed: %s", exc)

    out_days = []
    for back in range(days - 1, -1, -1):
        d = today_local - timedelta(days=back)
        date_text = d.isoformat()
        day_start = datetime(
            d.year, d.month, d.day, 0, 0,
            tzinfo=timezone(timedelta(minutes=tz_off)),
        )
        start_ms = int(day_start.astimezone(timezone.utc).timestamp() * 1000)
        end_ms = start_ms + 86_400_000
        # Look 18h past midnight so cross-midnight drain + full-recharge complete
        # (typical "back to 100%" lands ~12:00-14:00 the next day) are visible.
        look_end_ms = start_ms + 42 * 3_600_000
        pts = await history.query(serial, soc_field, start_ms, look_end_ms, max_points=240)
        analysis = (
            _analyze_day_cycle(pts, start_ms, end_ms, capacity_kwh) if pts else None
        )
        temps = temp_by_date.get(date_text) or {}
        out_days.append({
            "date": date_text,
            "start_ms": start_ms,
            "end_ms": end_ms,
            **(analysis or {"samples": len(pts)}),
            "temp_min_f": temps.get("temp_min_f"),
            "temp_max_f": temps.get("temp_max_f"),
            "temp_avg_f": temps.get("temp_avg_f"),
        })

    return {
        "serial": serial,
        "tz_offset_minutes": tz_off,
        "battery_capacity_kwh": capacity_kwh,
        "soc_field": soc_field,
        "days": out_days,
    }


# ---------------------------------------------------------------------------
# Widgets — server-side registry of self-describing dashboard tiles.
# Each widget has a stable id, metadata (description + JSON-schema-ish hints),
# config, and a cached "knowledge store" view that the LLM can introspect
# via REST or the matching MCP tools.
# ---------------------------------------------------------------------------


def _require_widget(widget_id: str):
    w = widget_registry.get(widget_id)
    if w is None:
        raise HTTPException(status_code=404, detail=f"unknown widget: {widget_id}")
    return w


async def _widget_payload(w, *, include_data: bool = True) -> dict[str, Any]:
    config = await widget_store.get_config(w.id) or dict(w.default_config)
    state = await widget_store.get_state(w.id)
    # Layout (tab + position) live in config so users can override per
    # widget. Fall back to the widget's class defaults.
    layout = {
        "tab": config.get("_tab") or w.default_tab,
        "position": int(config.get("_position", w.default_position)),
        "width":  max(1, min(3, int(config.get("_width",
                                              getattr(w, "default_width", 1))))),
        "height": max(1, min(3, int(config.get("_height",
                                               getattr(w, "default_height", 1))))),
    }
    body: dict[str, Any] = {
        "meta": w.meta(),
        "config": config,
        "layout": layout,
        "fetched_at": state.fetched_at if state else None,
        "error": state.error if state else None,
    }
    if include_data:
        body["data"] = state.data if state else None
    return body


@app.put(
    "/api/widgets/{widget_id}/layout",
    tags=["widgets"],
    summary="Set widget tab + position",
)
async def put_widget_layout(
    widget_id: str,
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Move a widget between tabs, change its position within a tab,
    or adjust its column/row span. Body: ``{"tab": "Safety",
    "position": 10, "width": 2, "height": 1}``. Any field is
    optional; omitted fields keep their current value.

    ``width`` and ``height`` are grid-cell spans (1–3). Default 1×1."""
    w = _require_widget(widget_id)
    config = await widget_store.get_config(w.id) or dict(w.default_config)
    if "tab" in body and body["tab"]:
        config["_tab"] = str(body["tab"])
    if "position" in body and body["position"] is not None:
        config["_position"] = int(body["position"])
    if "width" in body and body["width"] is not None:
        config["_width"] = max(1, min(3, int(body["width"])))
    if "height" in body and body["height"] is not None:
        config["_height"] = max(1, min(3, int(body["height"])))
    await widget_store.put_config(w.id, config)
    return {"id": w.id, **(await _widget_payload(w, include_data=False))}


@app.get("/api/widgets", tags=["widgets"], summary="List all widgets")
async def list_widgets(_: Session | None = Depends(read_or_public)):
    """Index of every registered widget plus its current cached payload.

    Each entry has: ``id``, ``meta`` (description, schemas, refresh policy),
    ``config`` (effective), ``data`` (last cached payload), ``fetched_at``,
    ``error``. Home-automation systems should poll this endpoint and read
    each widget's ``data`` field directly.
    """
    out = []
    for w in widget_registry.all():
        out.append({"id": w.id, **(await _widget_payload(w))})
    return {"widgets": out}


@app.get("/api/widgets/{widget_id}", tags=["widgets"], summary="Get one widget")
async def get_widget(widget_id: str, _: Session | None = Depends(read_or_public)):
    w = _require_widget(widget_id)
    return {"id": w.id, **(await _widget_payload(w))}


@app.get(
    "/api/widgets/{widget_id}/meta",
    tags=["widgets"],
    summary="Widget metadata",
)
async def get_widget_meta(widget_id: str, _: Session | None = Depends(read_or_public)):
    """Static metadata — schema, description, refresh policy. The
    "knowledge" half of the knowledge store; LLMs should call this to
    learn what fields to expect from ``/data``."""
    w = _require_widget(widget_id)
    return {"id": w.id, "meta": w.meta()}


@app.get(
    "/api/widgets/{widget_id}/data",
    tags=["widgets"],
    summary="Widget data (cached)",
)
async def get_widget_data(widget_id: str, _: Session | None = Depends(read_or_public)):
    w = _require_widget(widget_id)
    state = await widget_store.get_state(w.id)
    return {
        "id": w.id,
        "fetched_at": state.fetched_at if state else None,
        "error": state.error if state else None,
        "data": state.data if state else None,
    }


@app.get(
    "/api/widgets/{widget_id}/config",
    tags=["widgets"],
    summary="Widget config",
)
async def get_widget_config(widget_id: str, _: Session | None = Depends(read_or_public)):
    w = _require_widget(widget_id)
    config = await widget_store.get_config(w.id) or dict(w.default_config)
    return {"id": w.id, "config": config, "default_config": w.default_config}


@app.put(
    "/api/widgets/{widget_id}/config",
    tags=["widgets"],
    summary="Update widget config",
)
async def put_widget_config(
    widget_id: str,
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    w = _require_widget(widget_id)
    # Sheets-backed widgets: write the list_field to Sheets. Whole body
    # is still cached to widget_config as a fallback (so we survive a
    # Sheets outage / misconfigured tab).
    if sheets is not None and w.sheets_tab and w.sheets_list_field:
        items = body.get(w.sheets_list_field)
        if isinstance(items, list):
            try:
                await sheets.write(w.sheets_tab, w.sheets_field_order, items)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "sheets write for %s tab=%r failed: %s",
                    w.id, w.sheets_tab, exc,
                )
    await widget_store.put_config(w.id, body)
    # New config — pull fresh data immediately so the UI reflects the change
    # without waiting for the next refresh tick.
    await widget_refresh_now(w, widget_store, sheets, _SUBS_BUNDLE, mqtt)
    state = await widget_store.get_state(w.id)
    return {
        "id": w.id,
        "config": body,
        "fetched_at": state.fetched_at if state else None,
        "error": state.error if state else None,
    }


@app.get(
    "/api/widgets/{widget_id}/export.csv",
    tags=["widgets"],
    summary="Export the widget's cached data as CSV",
)
async def export_widget_csv(
    widget_id: str,
    _: Session | None = Depends(read_or_public),
):
    """Streams whatever's in the widget's cached data as CSV. Generic
    shape detection: (1) if the payload has a key whose value is a
    non-empty list of dicts, that becomes the rows; (2) otherwise the
    top-level dict is written as a single row of scalars. Widgets with
    an unusual shape can implement a ``csv_export(data)`` method
    returning ``(columns, rows)`` and it wins over generic detection."""
    import csv, io
    w = _require_widget(widget_id)
    state = await widget_store.get_state(w.id)
    if not state or not state.data:
        raise HTTPException(status_code=404, detail="no cached data")
    data = state.data
    columns: list[str]; rows: list[list]
    hook = getattr(w, "csv_export", None)
    if callable(hook):
        columns, rows = hook(data)
    else:
        columns, rows = _widget_data_to_csv(data)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{widget_id}.csv"'},
    )


def _widget_data_to_csv(data: Any) -> tuple[list[str], list[list]]:
    if isinstance(data, dict):
        # Prefer the first key mapping to a non-empty list of dicts
        for key, val in data.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                columns = sorted({
                    k for item in val for k in item.keys()
                    if not isinstance(item.get(k), (list, dict))
                })
                out_rows = [
                    [_scalar(item.get(c)) for c in columns] for item in val
                ]
                return columns, out_rows
        # Fall back to a single row of scalars
        columns, values = [], []
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                columns.append(k); values.append(_scalar(v))
        return columns, [values]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        columns = sorted({k for item in data for k in item.keys()})
        return columns, [[_scalar(item.get(c)) for c in columns] for item in data]
    return ["value"], [[str(data)]]


def _scalar(v: Any) -> Any:
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return "" if v is None else v


@app.get(
    "/metrics",
    tags=["metrics"],
    summary="Prometheus text-format metrics",
    include_in_schema=False,
)
async def prometheus_metrics():
    """No auth — for Prometheus scrapes. Bind Prometheus to localhost
    or firewall this port if you're paranoid."""
    from fastapi.responses import PlainTextResponse
    import time as _time
    lines: list[str] = []

    def gauge(name: str, help_text: str, samples: list[tuple[dict, float]]):
        if not samples:
            return
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        for labels, value in samples:
            lbl = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{lbl}}} {value}" if lbl else f"{name} {value}")

    now = _time.time()

    # Per-widget health
    fetched_age_samples: list[tuple[dict, float]] = []
    error_samples: list[tuple[dict, float]] = []
    for w in widget_registry.all():
        state = await widget_store.get_state(w.id)
        if state and state.fetched_at:
            fetched_age_samples.append(
                ({"widget": w.id}, round(now - float(state.fetched_at), 1))
            )
        error_samples.append(
            ({"widget": w.id},
             1 if (state and state.error) else 0)
        )
    gauge(
        "solarsage_widget_last_refresh_seconds",
        "Seconds since widget's last successful fetch",
        fetched_age_samples,
    )
    gauge(
        "solarsage_widget_error",
        "1 if widget has an error, 0 otherwise",
        error_samples,
    )

    # Solar telemetry from solar_vitals cached data
    sv = await widget_store.get_state("solar_vitals")
    if sv and sv.data and not sv.error:
        d = sv.data
        batt = d.get("battery") or {}
        solar = d.get("solar") or {}
        load = d.get("load") or {}
        bf = d.get("battery_flow") or {}
        for name, help_text, val in [
            ("solarsage_battery_soc_percent",
             "Battery state of charge (%)", batt.get("soc")),
            ("solarsage_battery_capacity_kwh",
             "Battery bank capacity (kWh)", batt.get("capacity_kwh")),
            ("solarsage_battery_kwh_remaining",
             "Battery kWh remaining", batt.get("kwh_remaining")),
            ("solarsage_solar_kw",
             "Live solar production (kW)", solar.get("total_kw")),
            ("solarsage_load_kw",
             "Live house load (kW)", load.get("kw")),
            ("solarsage_battery_charge_kw",
             "Battery charging rate (kW)", bf.get("charge_kw")),
            ("solarsage_battery_discharge_kw",
             "Battery discharging rate (kW)", bf.get("discharge_kw")),
        ]:
            if val is not None:
                gauge(name, help_text, [({}, float(val))])
        for st in solar.get("strings") or []:
            gauge(
                "solarsage_solar_string_kw",
                "Per-string PV production (kW)",
                [({"string": str(st.get("n"))}, float(st.get("kw") or 0))],
            )
        for r in (load.get("smart_ac_rooms") or []):
            gauge(
                "solarsage_ac_room_watts",
                "smart_ac room shown watts",
                [({"room": r.get("room", "")}, float(r.get("watts") or 0))],
            )
            gauge(
                "solarsage_ac_room_on",
                "smart_ac room on/off (1/0)",
                [({"room": r.get("room", "")}, 1 if r.get("on") else 0)],
            )
        for t in (load.get("room_sensors") or []):
            if t.get("temp_value") is not None:
                gauge(
                    "solarsage_room_temperature",
                    "Room temperature",
                    [({"room": t.get("name", ""),
                       "unit": t.get("temp_unit", "")},
                      float(t["temp_value"]))],
                )
            if t.get("humidity_value") is not None:
                gauge(
                    "solarsage_room_humidity_percent",
                    "Room relative humidity",
                    [({"room": t.get("name", "")},
                      float(t["humidity_value"]))],
                )

    # Water tank
    wt = await widget_store.get_state("water_tank")
    if wt and wt.data and not wt.error:
        d = wt.data
        for name, help_text, val in [
            ("solarsage_water_percent", "Water tank percent full",
             d.get("percent")),
            ("solarsage_water_gallons", "Water tank estimated gallons",
             d.get("gallons")),
            ("solarsage_water_gallons_per_day",
             "Water usage rate (gal/day)", d.get("gal_per_day")),
            ("solarsage_water_days_remaining",
             "Days until tank hits empty at current usage",
             d.get("days_remaining")),
        ]:
            if val is not None:
                gauge(name, help_text, [({}, float(val))])

    lines.append("")  # trailing newline
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.post(
    "/api/widgets/{widget_id}/refresh",
    tags=["widgets"],
    summary="Force refresh",
)
async def post_widget_refresh(
    widget_id: str,
    _: Session | None = Depends(require_read),
):
    w = _require_widget(widget_id)
    await widget_refresh_now(w, widget_store, sheets, _SUBS_BUNDLE, mqtt)
    return {"id": w.id, **(await _widget_payload(w))}


# ---------------------------------------------------------------------------
# Events + reminders.
# Events come from two sources: ``hoa`` (auto-extracted from the El Dorado
# Ranch weekly PDF) and ``manual`` (POSTed by the user). Each event carries
# a list of reminders ({minutes_before, mode, custom_text}); the reminder
# scheduler ticks every minute and fires reminders via the local TTS
# service. Home-automation systems can read /api/events/today to render
# today's agenda.
# ---------------------------------------------------------------------------


def _today_window_iso() -> tuple[str, str]:
    """Today bounds in the system local tz, ISO with offset."""
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _day_window_iso(offset_days: int) -> tuple[str, str]:
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start += timedelta(days=offset_days)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _reminders_from_payload(payload: list[dict[str, Any]]) -> list[ReminderRow]:
    out: list[ReminderRow] = []
    for item in payload or []:
        out.append(
            ReminderRow(
                id="",
                event_id="",
                minutes_before=int(item["minutes_before"]),
                mode=str(item.get("mode") or "tts"),
                custom_text=item.get("custom_text"),
            )
        )
    return out


@app.get(
    "/api/events",
    tags=["events"],
    summary="List events",
    description=(
        "All known events (HOA-extracted and manual) within an optional "
        "window. Each event lists its reminders so a UI or home-automation "
        "consumer can render the upcoming agenda."
    ),
)
async def list_events(
    starts_after: str | None = Query(default=None),
    starts_before: str | None = Query(default=None),
    today_only: bool = Query(default=False),
    _: Session | None = Depends(require_read),
):
    if today_only:
        starts_after, starts_before = _today_window_iso()
    events = await event_store.list_events(
        starts_after=starts_after, starts_before=starts_before,
    )
    return {"events": [event_to_dict(e) for e in events]}


@app.get("/api/events/today", tags=["events"], summary="Today's events")
async def list_events_today(_: Session | None = Depends(require_read)):
    """Convenience endpoint: today's events in the server's local tz.
    Use this from a Home Assistant template sensor or a wall display."""
    start, end = _today_window_iso()
    events = await event_store.list_events(
        starts_after=start, starts_before=end,
    )
    return {"date": start[:10], "events": [event_to_dict(e) for e in events]}


@app.get(
    "/api/events/upcoming",
    tags=["events"],
    summary="Today + next N days of events grouped by day",
)
async def list_events_upcoming(
    days: int = Query(default=2, ge=1, le=14),
    _: Session | None = Depends(require_read),
):
    """Returns events grouped by day: today, tomorrow, day-after, …
    ``days`` controls how many days to include (default 2 = today + tomorrow)."""
    start, _ignored = _day_window_iso(0)
    _s, end = _day_window_iso(days - 1)
    events = await event_store.list_events(
        starts_after=start, starts_before=end,
    )
    # Group into buckets by local date
    buckets: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        d = e.starts_at[:10]
        buckets.setdefault(d, []).append(event_to_dict(e))
    days_out = []
    for i in range(days):
        d_start, _ = _day_window_iso(i)
        d_key = d_start[:10]
        days_out.append({"date": d_key, "events": buckets.get(d_key, [])})
    return {"days": days_out}


@app.post("/api/events", tags=["events"], summary="Create manual event")
async def create_event(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Create a manual event. Required: ``title``, ``starts_at`` (ISO with
    tz). Optional: ``ends_at``, ``notes``, ``is_special``, ``reminders``
    (list of ``{minutes_before, mode, custom_text}``)."""
    try:
        title = str(body["title"])
        starts_at = str(body["starts_at"])
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"missing field: {exc}")
    reminders = _reminders_from_payload(body.get("reminders") or [])
    ev = EventRow(
        id="",
        source="manual",
        source_ref=None,
        title=title,
        starts_at=starts_at,
        ends_at=body.get("ends_at"),
        notes=body.get("notes"),
        is_special=bool(body.get("is_special", True)),
        reminders=reminders,
    )
    saved = await event_store.insert_manual(ev)
    fresh = await event_store.get(saved.id)
    return event_to_dict(fresh) if fresh else event_to_dict(saved)


@app.put("/api/events/{event_id}", tags=["events"], summary="Update event")
async def update_event(
    event_id: str,
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Patch any subset of: ``title``, ``starts_at``, ``ends_at``, ``notes``,
    ``is_special``, ``snoozed``. Touching the event marks it user-edited
    so the HOA ingest won't overwrite the changes on next refresh."""
    await event_store.update(
        event_id,
        title=body.get("title"),
        starts_at=body.get("starts_at"),
        ends_at=body.get("ends_at"),
        notes=body.get("notes"),
        is_special=body.get("is_special"),
        snoozed=body.get("snoozed"),
    )
    fresh = await event_store.get(event_id)
    if not fresh:
        raise HTTPException(status_code=404, detail="event not found")
    return event_to_dict(fresh)


@app.delete("/api/events/{event_id}", tags=["events"], summary="Delete event")
async def delete_event(
    event_id: str, _: Session | None = Depends(require_read),
):
    await event_store.delete(event_id)
    return {"ok": True}


@app.put(
    "/api/events/{event_id}/reminders",
    tags=["events"],
    summary="Set reminders for an event",
)
async def put_event_reminders(
    event_id: str,
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Replace this event's reminder list. Body: ``{"reminders": [{
    "minutes_before": 60, "mode": "tts", "custom_text": null}]}``.
    ``minutes_before=0`` means fire at start time."""
    reminders = _reminders_from_payload(body.get("reminders") or [])
    await event_store.set_reminders(event_id, reminders)
    fresh = await event_store.get(event_id)
    if not fresh:
        raise HTTPException(status_code=404, detail="event not found")
    return event_to_dict(fresh)


@app.post(
    "/api/events/{event_id}/say",
    tags=["events"],
    summary="Speak this event now (test reminder)",
)
async def post_event_say(
    event_id: str,
    _: Session | None = Depends(require_read),
):
    """Speak the event's title through the local TTS service immediately.
    Handy for testing audio routing without waiting for a real reminder."""
    ev = await event_store.get(event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="event not found")
    ok = await tts_say(f"Reminder: {ev.title}")
    return {"ok": ok}


@app.post(
    "/api/events/ingest_hoa",
    tags=["events"],
    summary="Force HOA event ingest",
)
async def post_ingest_hoa(_: Session | None = Depends(require_read)):
    """Trigger an out-of-band ingest of the HOA weekly PDF. Use this after
    PUTing a new HOA widget config or to pick up a freshly published PDF
    without waiting for the hourly tick."""
    await events_ingest_once(event_store, widget_store)
    return {"ok": True}


@app.post(
    "/api/translations",
    tags=["spanish"],
    summary="Translate text and log it",
)
async def post_translation(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Translate ``text`` from ``source`` (default ``en``) to ``target``
    (default ``es``) via MyMemory. Every lookup is persisted so the
    Spanish widget can show a rolling phrase book. Body:
    ``{"text": "hello", "source": "en", "target": "es"}``."""
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="missing text")
    source = str(body.get("source") or "en").lower()
    target = str(body.get("target") or "es").lower()
    try:
        translated = await mymemory_translate(text, source=source, target=target)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))
    tid = await translations_store.add(source, target, text, translated)
    return {
        "id": tid,
        "source": source,
        "target": target,
        "source_text": text,
        "target_text": translated,
    }


@app.get(
    "/api/translations",
    tags=["spanish"],
    summary="Recent translations log",
)
async def get_translations(
    limit: int = Query(default=50, ge=1, le=500),
    _: Session | None = Depends(require_read),
):
    """List the most-recent translations. Home automation can also poll
    this to build a lock-screen phrase book."""
    items = await translations_store.recent(limit=limit)
    return {"translations": items}


@app.post(
    "/api/translations/{tid}/star",
    tags=["spanish"],
    summary="Star / unstar a translation",
)
async def post_translation_star(
    tid: int,
    _: Session | None = Depends(require_read),
):
    await translations_store.toggle_star(tid)
    return {"ok": True}


@app.delete(
    "/api/translations/{tid}",
    tags=["spanish"],
    summary="Delete a translation",
)
async def delete_translation(
    tid: int,
    _: Session | None = Depends(require_read),
):
    await translations_store.delete(tid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# News archive + on-demand translation. Every fetched news item is stored
# in the news_items table; translation happens lazily on view.
# ---------------------------------------------------------------------------


@app.get(
    "/api/news/history",
    tags=["news"],
    summary="Full news archive for a widget",
)
async def get_news_history(
    widget_id: str = Query(default="baja_news"),
    limit: int = Query(default=100, ge=1, le=1000),
    translate_to: str | None = Query(default=None),
    translate_from: str = Query(default="es"),
    _: Session | None = Depends(require_read),
):
    """Return archived news items across all fetches for a widget.
    Useful for search / retrospection / building an offline history."""
    items = await news_store.recent(
        widget_id,
        translate_target=translate_to,
        translate_source=translate_from,
        limit=limit,
    )
    return {"widget_id": widget_id, "items": items}


@app.post(
    "/api/news/translate",
    tags=["news"],
    summary="Batch-translate a list of news item IDs",
)
async def post_news_translate(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{"ids":[1,2,3], "source":"es", "target":"en"}``.

    For each id, looks up the news_items row, then translates its
    title if not already cached. Returns ``{id: translated_title}``
    for successful translations. Uses the translations table as its
    cache — repeated calls for the same title are free."""
    ids = body.get("ids") or []
    source = str(body.get("source") or "es").lower()
    target = str(body.get("target") or "en").lower()
    out: dict[int, str] = {}
    for raw_id in ids:
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        item = await news_store.get(item_id)
        if not item:
            continue
        try:
            translated = await translations_store.translate_cached(
                source, target, item["title"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("news translate id=%s failed: %s", item_id, exc)
            continue
        out[item_id] = translated
    return {"translated": out}


# ---------------------------------------------------------------------------
# Notifications + threshold subscriptions.
# Notifications route through .notify.dispatch which knows about TTS
# (via the pi5 speaker) and Telegram (via Home Assistant's REST API).
# Rules stored in the subscriptions table are evaluated after every
# widget refresh; edge-triggered (false → true) on a per-rule cooldown.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rotation mode — fullscreen "screensaver" that cycles through widgets.
# Config stored as a JSON blob in widget_config under the special id
# ``_rotation``. Sequence entries are ordered; each has a widget_id and
# a per-item dwell_seconds so the user can weight what shows more
# (e.g. Solar every-other slot by adding it multiple times).
# ---------------------------------------------------------------------------

_ROTATION_ID = "_rotation"
_ROTATION_DEFAULT = {
    "enabled": False,
    "default_dwell_seconds": 20,
    "sequence": [
        {"widget_id": "solar_vitals", "dwell_seconds": 25},
        {"widget_id": "aqi",          "dwell_seconds": 15},
        {"widget_id": "solar_vitals", "dwell_seconds": 25},
        {"widget_id": "weather",      "dwell_seconds": 15},
        {"widget_id": "solar_vitals", "dwell_seconds": 25},
        {"widget_id": "tides",        "dwell_seconds": 20},
        {"widget_id": "solar_vitals", "dwell_seconds": 25},
        {"widget_id": "hoa",          "dwell_seconds": 15},
    ],
}


@app.get(
    "/api/rotation",
    tags=["rotation"],
    summary="Get rotation-mode config",
)
async def get_rotation(_: Session | None = Depends(read_or_public)):
    cur = await widget_store.get_config(_ROTATION_ID) or dict(_ROTATION_DEFAULT)
    return {"config": cur, "default": _ROTATION_DEFAULT}


@app.put(
    "/api/rotation",
    tags=["rotation"],
    summary="Save rotation-mode config",
)
async def put_rotation(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{enabled: bool, default_dwell_seconds: int,
    sequence: [{widget_id, dwell_seconds}]}``."""
    # Minimal validation — non-empty sequence, each item has a widget_id
    seq = body.get("sequence") or []
    if not isinstance(seq, list):
        raise HTTPException(status_code=400, detail="sequence must be a list")
    for i, item in enumerate(seq):
        if not isinstance(item, dict) or not item.get("widget_id"):
            raise HTTPException(
                status_code=400,
                detail=f"sequence[{i}] must be an object with widget_id",
            )
    await widget_store.put_config(_ROTATION_ID, body)
    return {"config": body}


# ---------------------------------------------------------------------------
# Announcements — per-source enable + warn-offsets + channels.
# Backed by widget_config under the special id ``_announcements``.
# ---------------------------------------------------------------------------


@app.get(
    "/api/announcements",
    tags=["announcements"],
    summary="Get auto-announcement config",
)
async def get_announcements(_: Session | None = Depends(read_or_public)):
    from . import announcements as ann
    saved = await widget_store.get_config(ann.CONFIG_ID) or {}
    return {
        "config": ann.merged_config(saved),
        "default": ann.DEFAULT_CONFIG,
    }


@app.put(
    "/api/announcements",
    tags=["announcements"],
    summary="Save auto-announcement config",
)
async def put_announcements(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{tides: {enabled, warn_minutes_before, channels, types,
    stations}, hoa: {...}, storms: {...}}``. Unknown sources pass
    through unchanged."""
    from . import announcements as ann
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    for src, cfg in body.items():
        if not isinstance(cfg, dict):
            raise HTTPException(
                status_code=400,
                detail=f"{src!r} must be an object",
            )
        offs = cfg.get("warn_minutes_before")
        if offs is not None and not (
            isinstance(offs, list)
            and all(isinstance(m, (int, float)) and m >= 0 for m in offs)
        ):
            raise HTTPException(
                status_code=400,
                detail=f"{src}.warn_minutes_before must be a list of >=0 numbers",
            )
        chans = cfg.get("channels")
        if chans is not None and not (
            isinstance(chans, list)
            and all(c in ("tts", "telegram", "log") for c in chans)
        ):
            raise HTTPException(
                status_code=400,
                detail=f"{src}.channels must be a subset of tts/telegram/log",
            )
    await widget_store.put_config(ann.CONFIG_ID, body)
    return {"config": ann.merged_config(body)}


@app.post(
    "/api/announcements/ingest",
    tags=["announcements"],
    summary="Force an immediate announcements ingest pass",
)
async def force_announcements_ingest(_: Session | None = Depends(require_read)):
    from . import announcements as ann
    saved = await widget_store.get_config(ann.CONFIG_ID) or {}
    counts = await ann.ingest_all(event_store, widget_store, saved)
    return {"ingested": counts}


@app.get(
    "/api/announcements/history",
    tags=["announcements"],
    summary="Recent announcement log entries (all sources)",
)
async def get_announcement_history(
    limit: int = 100,
    minutes: int | None = None,
    _: Session | None = Depends(read_or_public),
):
    """Recent announcements as JSON. ``minutes`` filters to the last
    N minutes; without it, returns the last ``limit`` rows."""
    since = minutes * 60 if minutes else None
    rows = await history.recent_announcements(limit=limit, since_seconds=since)
    return {"history": rows}


@app.post(
    "/api/announcements/replay",
    tags=["announcements"],
    summary="Re-fire announcements from the last N minutes",
)
async def replay_announcements(
    minutes: int = 15,
    channels: list[str] | None = None,
    _: Session | None = Depends(require_read),
):
    """Re-fires every announcement from the last N minutes. Optionally
    override the channels list — e.g. replay only via Telegram when the
    original went to TTS and you missed it."""
    from . import notify as notify_mod
    if minutes <= 0 or minutes > 24 * 60:
        raise HTTPException(status_code=400, detail="minutes must be 1..1440")
    rows = await history.recent_announcements(limit=200, since_seconds=minutes * 60)
    replayed = 0
    for row in rows:
        chans = channels if channels else row["channels"]
        for ch in chans:
            await notify_mod.dispatch({"type": ch, "text": row["text"]})
        await history.log_announcement(
            f"replay:{row['source']}", row["text"], chans, True,
            detail=f"replay of #{row['id']} from {row['ts']}",
        )
        replayed += 1
    return {"replayed": replayed}


@app.post(
    "/api/announcements/test",
    tags=["announcements"],
    summary="Fire a synthetic test announcement for one source",
)
async def test_announcement(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{"source": "tides"}``. Dispatches a "test message" via
    the configured channels for that source so the user can verify TTS
    + Telegram are actually working without waiting for a real event."""
    from . import announcements as ann
    from . import notify as notify_mod
    source = str(body.get("source") or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="source required")
    saved = await widget_store.get_config(ann.CONFIG_ID) or {}
    cfg = ann.merged_config(saved).get(source) or {}
    channels = cfg.get("channels") or ["tts"]
    text = f"SolarSage test — {source} channel check."
    outcomes = []
    for ch in channels:
        res = await notify_mod.dispatch({"type": ch, "text": text})
        outcomes.append({"channel": ch, **res})
    await history.log_announcement(
        f"test:{source}", text, channels,
        all(o.get("ok") for o in outcomes),
        detail=None,
    )
    return {"source": source, "text": text, "outcomes": outcomes}


# ---------------------------------------------------------------------------
# Solar-vitals calibration — write a measured wattage back to an
# appliance in the widget's config. Called by the frontend calibration
# modal after the user records "baseline" and "on" load readings and
# clicks Save (frontend supplies the delta).
# ---------------------------------------------------------------------------


@app.post(
    "/api/widgets/solar_vitals/calibrate",
    tags=["widgets"],
    summary="Save a measured wattage for a solar_vitals appliance",
)
async def calibrate_solar_vitals(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{"name": "AC — main", "watts": 3200}``. Updates that
    appliance's ``watts`` in the widget's config. If the appliance
    doesn't exist yet, it's added."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    try:
        watts = float(body.get("watts"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="watts must be numeric")
    if watts < 0:
        raise HTTPException(status_code=400, detail="watts must be non-negative")

    w = _require_widget("solar_vitals")
    config = await widget_store.get_config(w.id) or dict(w.default_config)
    appliances = list(config.get("appliances") or [])
    hit = False
    for a in appliances:
        if str(a.get("name") or "").strip().lower() == name.lower():
            a["watts"] = round(watts)
            a["calibrated_at"] = datetime.now(timezone.utc).isoformat()
            hit = True
            break
    if not hit:
        appliances.append({
            "name": name, "watts": round(watts), "on": False,
            "calibrated_at": datetime.now(timezone.utc).isoformat(),
        })
    config["appliances"] = appliances
    await widget_store.put_config(w.id, config)
    await widget_refresh_now(w, widget_store, sheets, _SUBS_BUNDLE, mqtt)
    return {"ok": True, "appliances": appliances}


# ---------------------------------------------------------------------------
# HA Integrations — one screen that lists every HA entity SolarSage
# consumes, shows its live value, and lets the user rebind it. The
# per-widget contract is the ``ha_entities_for(config)`` method on
# each Widget subclass.
# ---------------------------------------------------------------------------


async def _ha_get(path: str, params: dict | None = None) -> Any:
    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        return None
    headers = {"Authorization": f"Bearer {ha_token}"}
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"{ha_url}{path}", params=params, headers=headers, timeout=15,
            ) as r:
                if r.status >= 400:
                    return None
                return await r.json()
    except Exception:  # noqa: BLE001
        return None


@app.get(
    "/api/ha/integrations",
    tags=["ha"],
    summary="List every HA entity SolarSage consumes, per widget, "
            "with the current live value alongside.",
)
async def get_ha_integrations(_: Session | None = Depends(read_or_public)):
    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        raise HTTPException(
            status_code=503,
            detail="HA_URL + HA_TOKEN not set in backend/.env",
        )

    # Gather { entity_id: {state, friendly_name, unit, last_updated} } once
    all_states_payload = await _ha_get("/api/states") or []
    live: dict[str, dict[str, Any]] = {}
    for e in all_states_payload:
        eid = e.get("entity_id")
        if not eid:
            continue
        attrs = e.get("attributes") or {}
        live[eid] = {
            "state": e.get("state"),
            "friendly_name": attrs.get("friendly_name"),
            "unit": attrs.get("unit_of_measurement"),
            "last_updated": e.get("last_updated"),
        }

    out = []
    for w in widget_registry.all():
        entries_meta = getattr(w, "ha_entities", None)
        has_dynamic = w.ha_entities_for.__func__ is not Widget.ha_entities_for
        if not entries_meta and not has_dynamic:
            continue
        cfg = await widget_store.get_config(w.id) or dict(w.default_config)
        entries = w.ha_entities_for(cfg)
        if not entries:
            continue
        out.append({
            "widget_id": w.id,
            "widget_name": w.name,
            "widget_kind": w.kind,
            "entities": [
                {
                    **e,
                    "live": live.get(e.get("entity_id") or "") if e.get("entity_id") else None,
                }
                for e in entries
            ],
        })
    return {"integrations": out}


@app.put(
    "/api/ha/integrations/{widget_id}",
    tags=["ha"],
    summary="Rebind one or more HA entity keys for a widget.",
)
async def put_ha_integration(
    widget_id: str,
    body: dict[str, str],
    _: Session | None = Depends(require_read),
):
    """Body: ``{"ha_entity_id": "sensor.foo", "smart_ac_status_entity": "sensor.bar"}``.
    Only keys declared in the widget's ``ha_entities`` list can be
    updated (dynamic ``smart_ac_room:*`` / ``appliance:*`` entries are
    read-only). Any listed entity_id must resolve in HA."""
    w = _require_widget(widget_id)
    static_keys = {e["key"] for e in (getattr(w, "ha_entities", None) or [])}
    if not static_keys:
        raise HTTPException(
            status_code=400, detail=f"{widget_id} has no editable HA entities",
        )
    unknown = [k for k in body if k not in static_keys]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"unknown or read-only keys: {unknown}. "
                   f"editable: {sorted(static_keys)}",
        )

    # Validate every entity_id resolves in HA (allow empty string = unset)
    for k, v in body.items():
        if not v:
            continue
        state = await _ha_get(f"/api/states/{v}")
        if not state:
            raise HTTPException(
                status_code=400,
                detail=f"{k}={v!r}: HA doesn't recognise that entity",
            )

    cfg = await widget_store.get_config(w.id) or dict(w.default_config)
    for k, v in body.items():
        cfg[k] = v or None
    await widget_store.put_config(w.id, cfg)
    try:
        await widget_refresh_now(w, widget_store, sheets, _SUBS_BUNDLE, mqtt)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "widget_id": widget_id, "updated": list(body)}


@app.get(
    "/api/ha/entities",
    tags=["ha"],
    summary="Search HA entities by id substring or friendly name; "
            "backs the autocomplete in the Integrations tab.",
)
async def search_ha_entities(
    q: str = "",
    domain: str | None = None,
    limit: int = 25,
    _: Session | None = Depends(read_or_public),
):
    payload = await _ha_get("/api/states") or []
    q = q.strip().lower()
    hits: list[dict[str, Any]] = []
    for e in payload:
        eid = str(e.get("entity_id") or "")
        if domain and not eid.startswith(f"{domain}."):
            continue
        attrs = e.get("attributes") or {}
        friendly = str(attrs.get("friendly_name") or "")
        if q and q not in eid.lower() and q not in friendly.lower():
            continue
        hits.append({
            "entity_id": eid,
            "friendly_name": friendly,
            "state": e.get("state"),
            "unit": attrs.get("unit_of_measurement"),
        })
        if len(hits) >= limit:
            break
    return {"entities": hits}


SMART_AC_ROOMS = {"master", "guest", "dining", "living", "office", "kyle"}


@app.post(
    "/api/smart_ac/override",
    tags=["smart_ac"],
    summary="Turn a smart_ac room on/off with an optional pin duration",
)
async def smart_ac_override(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{"room": "living", "state": "on"|"off",
    "duration_minutes": 60}`` OR ``{..., "until": "YYYY-MM-DD HH:MM:SS"}``.
    Calls Home Assistant to flip ``input_boolean.ac_<room>`` and pins
    ``input_datetime.ac_<room>_override_until`` so the smart_ac
    scheduler leaves the room alone until that time.

    * ``duration_minutes > 0``: pin until (now + N minutes). Cap 10 days
      so the scheduler can never be pinned indefinitely by accident.
    * ``until``: absolute local-time datetime. Same 10-day cap.
    * both missing / duration=0 / until in the past: clears any existing
      override so the scheduler resumes control on its next 5-min tick.

    See ~/code/claude_world/homeassistant for the scheduler that
    reads these entities.
    """
    room = str(body.get("room") or "").strip().lower()
    state = str(body.get("state") or "").strip().lower()
    duration = int(body.get("duration_minutes") or 0)
    until_raw = str(body.get("until") or "").strip()

    if room not in SMART_AC_ROOMS:
        raise HTTPException(
            status_code=400,
            detail=f"room must be one of {sorted(SMART_AC_ROOMS)}",
        )
    if state not in ("on", "off"):
        raise HTTPException(status_code=400, detail="state must be 'on' or 'off'")
    max_minutes = 10 * 24 * 60  # 10 days
    if duration < 0 or duration > max_minutes:
        raise HTTPException(
            status_code=400,
            detail=f"duration_minutes must be 0..{max_minutes}",
        )

    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        raise HTTPException(
            status_code=500, detail="HA_URL + HA_TOKEN not set in backend/.env",
        )

    boolean_eid = f"input_boolean.ac_{room}"
    dt_eid = f"input_datetime.ac_{room}_override_until"

    # 1. Flip the boolean
    service = "turn_on" if state == "on" else "turn_off"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{ha_url}/api/services/input_boolean/{service}",
            json={"entity_id": boolean_eid},
            headers=headers, timeout=10,
        ) as r:
            if r.status >= 400:
                text = (await r.text())[:200]
                raise HTTPException(
                    status_code=502,
                    detail=f"HA {service} failed: {r.status} {text}",
                )

        # 2. Set / clear the override datetime
        until: datetime | None = None
        now_local = datetime.now().astimezone()
        if until_raw:
            # Accept ISO ("2026-07-04T14:00") or "YYYY-MM-DD HH:MM[:SS]".
            # datetime.fromisoformat handles both since 3.11.
            parsed: datetime | None = None
            try:
                parsed = datetime.fromisoformat(until_raw.replace("T", " "))
            except ValueError:
                pass
            if parsed is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"until must be ISO datetime, got {until_raw!r}",
                )
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now_local.tzinfo)
            if parsed > now_local + timedelta(minutes=max_minutes):
                raise HTTPException(
                    status_code=400,
                    detail=f"until is more than {max_minutes // 1440} days out",
                )
            if parsed > now_local:
                until = parsed
        elif duration > 0:
            until = now_local + timedelta(minutes=duration)

        if until is not None:
            dt_str = until.strftime("%Y-%m-%d %H:%M:%S")
        else:
            dt_str = "1970-01-01 00:00:00"
        async with http.post(
            f"{ha_url}/api/services/input_datetime/set_datetime",
            json={"entity_id": dt_eid, "datetime": dt_str},
            headers=headers, timeout=10,
        ) as r:
            if r.status >= 400:
                text = (await r.text())[:200]
                # Boolean was flipped, but override didn't set — return
                # a partial-success so the caller can decide.
                return {
                    "ok": False,
                    "detail": f"boolean flipped but override failed: {r.status} {text}",
                    "room": room, "state": state,
                }

    # Force a solar_vitals refresh so the widget reflects the change immediately
    try:
        w = _require_widget("solar_vitals")
        await widget_refresh_now(w, widget_store, sheets, _SUBS_BUNDLE, mqtt)
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "room": room,
        "state": state,
        "duration_minutes": duration,
        "override_until": until.isoformat() if until else None,
    }


# --- DAB water-pump control ------------------------------------------------

# Maps the widget's short ``action`` verb → (HA service, payload) tuples.
# Payload uses ``{entity_id}`` as a placeholder; the endpoint substitutes
# the configured entity id per action so each install can retarget in
# Settings if the entity slugs differ.
_DAB_ACTIONS: dict[str, tuple[str, str, str, str]] = {
    # action                domain         service          entity-key                    value
    "sleep_on":            ("switch",      "turn_on",       "sleep_switch_eid",           ""),
    "sleep_off":           ("switch",      "turn_off",      "sleep_switch_eid",           ""),
    "power_shower_start":  ("select",      "select_option", "power_shower_select_eid",    "Start"),
    "power_shower_stop":   ("select",      "select_option", "power_shower_select_eid",    "Stop"),
    "pump_enable":         ("select",      "select_option", "pump_disable_select_eid",    "Enable"),
    "pump_disable":        ("select",      "select_option", "pump_disable_select_eid",    "Disable"),
    "set_boost":           ("select",      "select_option", "power_shower_boost_eid",     "__value__"),
    "set_reduction":       ("select",      "select_option", "sleep_reduction_eid",        "__value__"),
}


@app.post(
    "/api/widgets/dab_pump/control",
    tags=["widgets"],
    summary="Trigger a DAB e.syMINI pump action via Home Assistant",
)
async def dab_pump_control(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{"action": "power_shower_start"}`` — or with a value for
    the two ``set_*`` actions, e.g. ``{"action":"set_boost","value":"+ 40"}``.

    Reads the target HA entity id from the ``dab_pump_control`` widget's
    stored config so it survives across installs with different pump
    entity slugs.
    """
    action = str(body.get("action") or "").strip().lower()
    if action not in _DAB_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of {sorted(_DAB_ACTIONS)}",
        )

    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        raise HTTPException(
            status_code=500, detail="HA_URL + HA_TOKEN not set in backend/.env",
        )

    domain, service, config_key, canned_value = _DAB_ACTIONS[action]

    w = widget_registry.get("dab_pump_control")
    if w is None:
        raise HTTPException(status_code=500, detail="dab_pump_control not registered")
    config = await widget_store.get_config(w.id) or {}
    merged = {**(w.default_config or {}), **config}
    entity_id = (merged.get(config_key) or "").strip()
    if not entity_id:
        raise HTTPException(
            status_code=400,
            detail=f"{config_key} not configured for dab_pump_control",
        )

    payload: dict[str, Any] = {"entity_id": entity_id}
    if canned_value == "__value__":
        supplied = str(body.get("value") or "").strip()
        if not supplied:
            raise HTTPException(
                status_code=400,
                detail="action requires a 'value' (e.g. '+ 40', '- 30')",
            )
        payload["option"] = supplied
    elif canned_value:
        payload["option"] = canned_value

    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{ha_url}/api/services/{domain}/{service}",
            json=payload, headers=headers, timeout=10,
        ) as r:
            if r.status >= 400:
                text = (await r.text())[:200]
                raise HTTPException(
                    status_code=502,
                    detail=f"HA {domain}/{service} failed: {r.status} {text}",
                )

    # Force a control-widget refresh so the toggle state flips right
    # away instead of waiting for the next scheduled tick.
    try:
        await widget_refresh_now(w, widget_store, sheets, _SUBS_BUNDLE, mqtt)
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "action": action, "entity_id": entity_id}


@app.post(
    "/api/notify/test",
    tags=["notify"],
    summary="Fire one notification action for testing",
)
async def post_notify_test(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: an action dict, e.g. ``{"type":"telegram","text":"hi"}``
    or ``{"type":"tts","text":"hola"}``. Returns the channel's
    ok/detail so you can verify HA_URL / HA_TOKEN / TTS routing."""
    result = await _notify.dispatch(body)
    return result


@app.get(
    "/api/subscriptions",
    tags=["subscriptions"],
    summary="List all subscription rules",
)
async def list_subscriptions(_: Session | None = Depends(require_read)):
    subs = await subscriptions_store.list_all()
    return {"subscriptions": subs}


@app.post(
    "/api/subscriptions",
    tags=["subscriptions"],
    summary="Create or update a subscription rule",
)
async def upsert_subscription(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Body: ``{id?, widget_id, name, condition:{path,op,value},
    message, actions:[{type,...}], enabled?, cooldown_minutes?}``.
    Pass an id to update; omit for create."""
    try:
        saved = await subscriptions_store.upsert(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return saved


@app.delete(
    "/api/subscriptions/{sub_id}",
    tags=["subscriptions"],
    summary="Delete a subscription rule",
)
async def delete_subscription(
    sub_id: str, _: Session | None = Depends(require_read),
):
    await subscriptions_store.delete(sub_id)
    return {"ok": True}


@app.post(
    "/api/subscriptions/{sub_id}/test",
    tags=["subscriptions"],
    summary="Fire this rule's actions right now (bypass condition + cooldown)",
)
async def test_subscription(
    sub_id: str, _: Session | None = Depends(require_read),
):
    sub = await subscriptions_store.get(sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="subscription not found")
    rule = sub["rule"]
    # Render against the widget's current data if we can
    state = await widget_store.get_state(sub["widget_id"])
    data = state.data if state else {}
    message = _notify_render(rule.get("message", ""), data) or rule.get("name", "")
    results = await _notify.dispatch_all(
        rule.get("actions") or [], default_text=message,
    )
    return {"id": sub_id, "message": message, "results": results}


def _notify_render(template: str, data: Any) -> str:
    from .subscriptions import render_message
    return render_message(template, data)


@app.post("/api/tts/say", tags=["tts"], summary="Speak arbitrary text")
async def post_tts_say(
    body: dict[str, Any],
    _: Session | None = Depends(require_read),
):
    """Generic passthrough to the local TTS service. Body:
    ``{"text": "anything you want spoken"}``. Used by the per-event
    test button and exposed so home automation can use it too."""
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="missing text")
    ok = await tts_say(text)
    return {"ok": ok}


@app.get("/api/health")
async def health():
    return {"ok": True, "base_url": BASE_URL, "poll_interval": POLL_INTERVAL}
