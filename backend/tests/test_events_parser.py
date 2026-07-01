"""HOA event parser: day-header parsing, AM/PM heuristics, event
classification."""

from __future__ import annotations

from datetime import date, datetime

from app.events import parser as P


def test_am_pm_leading_zero_wins():
    # "08:00 4th of July Golf Tournament" — leading zero forces AM
    h, m = P._to_24h(8, 0, "4th of July Golf Tournament",
                     day_block="", leading_zero=True)
    assert (h, m) == (8, 0)


def test_am_pm_evening_keyword_forces_pm():
    h, m = P._to_24h(6, 30, "Movie Night", day_block="",
                     leading_zero=False)
    assert (h, m) == (18, 30)


def test_am_pm_defaults_to_morning():
    h, m = P._to_24h(7, 30, "Lap Swimming", day_block="",
                     leading_zero=False)
    assert (h, m) == (7, 30)


def test_am_pm_after_noon_anchor_becomes_pm():
    block = "7:30 morning stuff\n12:00 noon\n1:00 Bingo\n"
    h, m = P._to_24h(1, 0, "Bingo", day_block=block, leading_zero=False)
    assert (h, m) == (13, 0)


def test_classify_routine_vs_special():
    assert P._classify("Lap Swimming") is False
    assert P._classify("Water Volleyball – Cachanilla Pools") is False
    assert P._classify("Movie Night") is True
    assert P._classify("FULL MOON MIXER") is True
    assert P._classify("Poker Tournament @Pavilion") is True


def test_week_anchor_from_title_finds_start_date():
    text = "Weekly Activities Schedule: June 29 – 5 July 2026\n..."
    anchor = P._week_anchor_from_title(text, date(2026, 1, 1))
    assert anchor == date(2026, 6, 29)


def test_week_anchor_falls_back_when_no_title():
    fallback = date(2026, 6, 29)
    anchor = P._week_anchor_from_title("no title here", fallback)
    assert anchor == fallback


def test_split_day_blocks():
    text = """
    Monday June 29th

    7:30 Lap Swimming

    Tuesday 30th

    6:30 Movie Night
    """
    blocks = P._split_day_blocks(text)
    days = [b[0] for b in blocks]
    assert "monday" in days
    assert "tuesday" in days


def test_resolve_date_advances_by_dow():
    anchor = date(2026, 6, 29)  # Monday
    assert P._resolve_date("Monday June 29th", "monday", anchor) == date(2026, 6, 29)
    assert P._resolve_date("Tuesday 30th",     "tuesday", anchor) == date(2026, 6, 30)
    assert P._resolve_date("Wednesday July 1st", "wednesday", anchor) == date(2026, 7, 1)
    assert P._resolve_date("Sunday 5th",       "sunday", anchor) == date(2026, 7, 5)
