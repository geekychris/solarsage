"""Notification dispatcher — channels, dispatch, dispatch_all."""

from __future__ import annotations

import pytest

from app import notify as _n


@pytest.mark.asyncio
async def test_channels_registered():
    """Ships with tts, telegram, log by default."""
    assert "tts" in _n.CHANNELS
    assert "telegram" in _n.CHANNELS
    assert "log" in _n.CHANNELS


@pytest.mark.asyncio
async def test_dispatch_log_channel():
    r = await _n.dispatch({"type": "log", "text": "hello"})
    assert r == {"ok": True, "detail": "logged"}


@pytest.mark.asyncio
async def test_dispatch_unknown_channel():
    r = await _n.dispatch({"type": "smoke_signal", "text": "hi"})
    assert r["ok"] is False
    assert "unknown channel" in r["detail"]


@pytest.mark.asyncio
async def test_dispatch_empty_text_rejected():
    r = await _n.dispatch({"type": "log", "text": ""})
    assert r == {"ok": False, "detail": "empty text"}


@pytest.mark.asyncio
async def test_dispatch_uses_default_text():
    r = await _n.dispatch({"type": "log"}, default_text="from-default")
    assert r == {"ok": True, "detail": "logged"}


@pytest.mark.asyncio
async def test_dispatch_all_multiple():
    actions = [{"type": "log"}, {"type": "log"}]
    results = await _n.dispatch_all(actions, default_text="x")
    assert len(results) == 2
    assert all(r["ok"] for r in results)
    assert all(r["channel"] == "log" for r in results)


@pytest.mark.asyncio
async def test_telegram_missing_env_returns_error(monkeypatch):
    monkeypatch.delenv("HA_URL", raising=False)
    monkeypatch.delenv("HA_TOKEN", raising=False)
    r = await _n.dispatch({"type": "telegram", "text": "hi"})
    assert r["ok"] is False
    assert "HA_URL" in r["detail"]


@pytest.mark.asyncio
async def test_telegram_invalid_service(monkeypatch):
    monkeypatch.setenv("HA_URL", "http://x")
    monkeypatch.setenv("HA_TOKEN", "y")
    r = await _n.dispatch({"type": "telegram", "text": "hi", "service": "no_dot"})
    assert r["ok"] is False
    assert "invalid service" in r["detail"]


@pytest.mark.asyncio
async def test_telegram_target_from_env(monkeypatch):
    """When per-action target is missing, NOTIFY_TELEGRAM_TARGET is used
    and numeric strings are coerced to int for HA."""
    monkeypatch.setenv("HA_URL", "http://x")
    monkeypatch.setenv("HA_TOKEN", "y")
    monkeypatch.setenv("NOTIFY_TELEGRAM_TARGET", "12345")

    captured = {}

    class _FakeResp:
        status = 200
        async def text(self): return "ok"

    class _FakeCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def text(self): return "ok"
        status = 200

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeCtx()

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _FakeSession())

    r = await _n.dispatch({"type": "telegram", "text": "hi",
                           "service": "telegram_bot.send_message"})
    assert r["ok"] is True
    assert captured["json"]["target"] == 12345  # coerced to int


@pytest.mark.asyncio
async def test_telegram_target_comma_list(monkeypatch):
    monkeypatch.setenv("HA_URL", "http://x")
    monkeypatch.setenv("HA_TOKEN", "y")
    monkeypatch.setenv("NOTIFY_TELEGRAM_TARGET", "111,222,333")

    captured = {}

    class _FakeCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def text(self): return "ok"
        status = 200

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        def post(self, url, json=None, headers=None, timeout=None):
            captured["json"] = json
            return _FakeCtx()

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: _FakeSession())

    await _n.dispatch({"type": "telegram", "text": "hi",
                       "service": "telegram_bot.send_message"})
    assert captured["json"]["target"] == [111, 222, 333]
