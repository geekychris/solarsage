"""Sheets value coercion — cells come back as strings, widgets want
booleans, lists, ints."""

from __future__ import annotations

from app import sheets as S


def test_from_cell_booleans():
    for v in ("TRUE", "true", "yes", "1"):
        assert S._from_cell(v, "checked") is True
    for v in ("FALSE", "no", "0", "", None):
        assert S._from_cell(v, "checked") is False


def test_from_cell_tags_split():
    assert S._from_cell("hoa, emergency", "tags") == ["hoa", "emergency"]
    assert S._from_cell("hoa; food", "tags") == ["hoa", "food"]
    assert S._from_cell("", "tags") == []
    assert S._from_cell(None, "tags") is None
    # Empty string → empty list
    assert S._from_cell("", "tags") == []


def test_from_cell_ints():
    assert S._from_cell("42", "wait_min") == 42
    assert S._from_cell("3", "priority") == 3
    assert S._from_cell("not a number", "wait_min") is None


def test_from_cell_floats_when_int_fails():
    # kwh accepts either int or float; falls through to float on
    # a non-integer numeric string
    assert S._from_cell("4.5", "kwh") == 4.5


def test_to_cell_serialization():
    assert S._to_cell(True) == "TRUE"
    assert S._to_cell(False) == "FALSE"
    assert S._to_cell(["a", "b"]) == "a, b"
    assert S._to_cell(("x",)) == "x"
    assert S._to_cell(None) == ""
    assert S._to_cell(42) == 42
    assert S._to_cell("hello") == "hello"


def test_col_letter():
    assert S._col_letter(1) == "A"
    assert S._col_letter(6) == "F"
    assert S._col_letter(26) == "Z"
    assert S._col_letter(27) == "AA"
    assert S._col_letter(52) == "AZ"


def test_load_sheets_from_env_returns_none_without_config(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("SOLARSAGE_SHEET_ID", raising=False)
    assert S.load_sheets_from_env() is None


def test_load_sheets_from_env_returns_none_when_key_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/nonexistent/path")
    monkeypatch.setenv("SOLARSAGE_SHEET_ID", "abc")
    assert S.load_sheets_from_env() is None
