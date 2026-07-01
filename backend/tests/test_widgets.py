"""Every registered widget class instantiates, meta is sane, config
schema matches default_config, sheets attrs are consistent."""

from __future__ import annotations

import inspect

import pytest

# Import each widget module and its widget class
from app.widgets import Widget, registry
from app.widgets.base import Widget as WidgetBase
from app.widgets.tide import TideWidget
from app.widgets.border import BorderWidget
from app.widgets.hoa import HoaWidget
from app.widgets.safety_quakes import QuakesWidget
from app.widgets.safety_storms import StormsWidget
from app.widgets.safety_uv import UvHeatWidget
from app.widgets.safety_aqi import AqiWidget
from app.widgets.weather import WeatherWidget
from app.widgets.outdoor_marine import MarineWidget
from app.widgets.outdoor_sunmoon import SunMoonWidget
from app.widgets.outdoor_fishing import FishingWindowWidget
from app.widgets.sea_temp import SeaTempWidget
from app.widgets.whale_season import WhaleSeasonWidget
from app.widgets.trip_planner import TripPlannerWidget
from app.widgets.return_countdown import ReturnCountdownWidget
from app.widgets.travel_currency import CurrencyWidget
from app.widgets.costco_fuel import CostcoFuelWidget
from app.widgets.travel_drive import DriveTimeWidget
from app.widgets.travel_holidays import HolidaysWidget
from app.widgets.border_log import BorderLogWidget
from app.widgets.shopping_list import ShoppingListWidget
from app.widgets.property_mode import PropertyModeWidget
from app.widgets.solar_excess import SolarExcessWidget
from app.widgets.solar_precool import PrecoolWidget
from app.widgets.consumption_yoy import ConsumptionYoYWidget
from app.widgets.community_newsletter import NewsletterWidget
from app.widgets.news import NewsWidget
from app.widgets.baja_news import BajaNewsWidget
from app.widgets.baja_races import BajaRacesWidget
from app.widgets.reservations import ReservationsWidget
from app.widgets.quicklinks import QuickLinksWidget
from app.widgets.property_tax import PropertyTaxWidget
from app.widgets.contacts import ContactsWidget
from app.widgets.todo import TodoWidget
from app.widgets.spanish import SpanishWidget


ALL_WIDGET_CLASSES = [
    TideWidget, BorderWidget, HoaWidget,
    QuakesWidget, StormsWidget, UvHeatWidget, AqiWidget,
    WeatherWidget, MarineWidget, SunMoonWidget,
    FishingWindowWidget, SeaTempWidget, WhaleSeasonWidget,
    TripPlannerWidget, ReturnCountdownWidget, CurrencyWidget,
    CostcoFuelWidget, DriveTimeWidget, HolidaysWidget,
    BorderLogWidget, ShoppingListWidget,
    PropertyModeWidget, SolarExcessWidget, PrecoolWidget,
    ConsumptionYoYWidget,
    NewsletterWidget, NewsWidget, BajaNewsWidget, BajaRacesWidget,
    ReservationsWidget, QuickLinksWidget, PropertyTaxWidget,
    ContactsWidget, TodoWidget, SpanishWidget,
]


@pytest.mark.parametrize("cls", ALL_WIDGET_CLASSES,
                         ids=lambda c: c.__name__)
def test_widget_class_meta(cls):
    """Every widget has the mandatory metadata fields set."""
    w = cls()
    assert w.id, f"{cls.__name__}: id must be set"
    assert w.kind, f"{cls.__name__}: kind must be set"
    assert w.name, f"{cls.__name__}: name must be set"
    assert w.description, f"{cls.__name__}: description must be set"
    assert w.refresh_seconds >= 60, (
        f"{cls.__name__}: refresh_seconds too small "
        f"({w.refresh_seconds}s) — will be clamped by the refresher"
    )
    assert isinstance(w.default_tab, str) and w.default_tab, (
        f"{cls.__name__}: default_tab required"
    )
    assert isinstance(w.default_position, int)


@pytest.mark.parametrize("cls", ALL_WIDGET_CLASSES,
                         ids=lambda c: c.__name__)
def test_widget_fetch_is_coroutine(cls):
    """fetch() must be an async coroutine function."""
    w = cls()
    assert inspect.iscoroutinefunction(w.fetch), (
        f"{cls.__name__}: fetch() must be async"
    )


@pytest.mark.parametrize("cls", ALL_WIDGET_CLASSES,
                         ids=lambda c: c.__name__)
def test_widget_default_config_matches_schema(cls):
    """Every key in default_config should be declared in config_schema
    (or the schema is deliberately open-ended)."""
    w = cls()
    schema = w.config_schema or {}
    props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
    if not props:
        return  # nothing to check — widget accepts arbitrary config
    for k in (w.default_config or {}):
        assert k in props, (
            f"{cls.__name__}: default_config key {k!r} not in "
            f"config_schema.properties ({list(props)})"
        )


def test_widget_ids_are_unique():
    ids = [w.id for w in ALL_WIDGET_CLASSES]
    assert len(ids) == len(set(ids)), (
        f"duplicate widget ids: "
        f"{[i for i in ids if ids.count(i) > 1]}"
    )


def test_widget_sheets_attrs_consistent():
    """If sheets_tab is set, sheets_list_field + sheets_field_order
    must also be set."""
    for cls in ALL_WIDGET_CLASSES:
        w = cls()
        if not w.sheets_tab:
            continue
        assert w.sheets_list_field, (
            f"{cls.__name__}: has sheets_tab but no sheets_list_field"
        )
        assert w.sheets_field_order, (
            f"{cls.__name__}: has sheets_tab but no sheets_field_order"
        )


def test_widget_meta_serializable():
    """The meta dict is what LLMs see via /api/widgets/<id>/meta — it
    must be plain JSON-safe types."""
    import json
    for cls in ALL_WIDGET_CLASSES:
        w = cls()
        json.dumps(w.meta())  # raises if unserializable


def test_registry_registers_without_dupes(tmp_db_path):
    from app.widgets.registry import WidgetRegistry
    r = WidgetRegistry()
    for cls in ALL_WIDGET_CLASSES:
        r.register(cls())
    assert len(list(r.all())) == len(ALL_WIDGET_CLASSES)
    # Registering the same id twice raises
    with pytest.raises(ValueError):
        r.register(TideWidget())
