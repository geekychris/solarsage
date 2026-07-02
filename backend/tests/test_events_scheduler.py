"""Reminder-text formatting — must render in the listener's local
timezone, not UTC. Regression test for the "10:53 pm" tide bug
(a UTC 22:53 tide was announced as "10:53 pm" and the listener read
it as their own 10:53 pm — nine hours off)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.events.scheduler import _format_reminder_text


def test_reminder_text_converts_to_local_tz(monkeypatch):
    # Force the process TZ so the assertion is deterministic across
    # dev laptops and CI runners.
    monkeypatch.setenv("TZ", "America/Tijuana")
    try:
        import time as _time
        _time.tzset()
    except AttributeError:
        pass

    # A tide extreme published as UTC 22:53 == 15:53 PDT (UTC-7).
    tide_utc = datetime(2026, 7, 2, 22, 53, tzinfo=timezone.utc)
    text = _format_reminder_text("High tide at Puertecitos", tide_utc, 120)

    assert "3:53 pm" in text.lower(), text
    assert "10:53" not in text, "leaked UTC hour into the message"


def test_short_reminder_uses_minutes(monkeypatch):
    monkeypatch.setenv("TZ", "America/Tijuana")
    try:
        import time as _time
        _time.tzset()
    except AttributeError:
        pass
    tide_utc = datetime(2026, 7, 2, 22, 53, tzinfo=timezone.utc)
    text = _format_reminder_text("High tide", tide_utc, 30)
    assert "in about 30 minutes" in text


def test_long_reminder_uses_hours(monkeypatch):
    monkeypatch.setenv("TZ", "America/Tijuana")
    try:
        import time as _time
        _time.tzset()
    except AttributeError:
        pass
    tide_utc = datetime(2026, 7, 2, 22, 53, tzinfo=timezone.utc)
    text = _format_reminder_text("Sunset viewing", tide_utc, 120)
    assert "in about 2 hours" in text


def test_reminder_text_naive_datetime_treated_as_local():
    # A naive datetime (no tz) is left as-is — legacy call sites
    # that happen to pass local-naive shouldn't be shifted twice.
    naive = datetime(2026, 7, 2, 15, 53)
    text = _format_reminder_text("High tide", naive, 30)
    assert "3:53 pm" in text.lower()
