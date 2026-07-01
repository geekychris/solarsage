"""Shared pytest fixtures — mostly a temp-DB path per test."""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

# Make ``app`` importable when running pytest from anywhere
_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))


@pytest.fixture
def tmp_db_path(tmp_path):
    """A fresh SQLite path per test so state doesn't leak."""
    p = tmp_path / "test.db"
    old = os.environ.get("EG4_DB_PATH")
    os.environ["EG4_DB_PATH"] = str(p)
    try:
        yield str(p)
    finally:
        if old is None:
            os.environ.pop("EG4_DB_PATH", None)
        else:
            os.environ["EG4_DB_PATH"] = old
