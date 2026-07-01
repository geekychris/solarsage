"""Notification dispatcher: send a message through TTS / Telegram / push.

Channels are pluggable — each is a small async function that takes a
text (+ any channel-specific kwargs) and returns ``{ok, detail}``.
The subscription evaluator calls ``dispatch(action)`` for each rule
action; the test-notify endpoint calls it directly.

Telegram uses Home Assistant's ``notify.telegram`` service via HA's
REST API. That way HA owns the bot token and message routing; we just
POST to it. Set ``HA_URL`` + ``HA_TOKEN`` in ``backend/.env``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

from .events.tts import say as _tts_say

log = logging.getLogger("eg4.notify")


# --- Channel implementations -------------------------------------------

async def _tts(text: str, **_) -> dict[str, Any]:
    ok = await _tts_say(text)
    return {"ok": ok, "detail": "spoke via local TTS"}


async def _telegram(
    text: str,
    *,
    service: str | None = None,
    target: str | list[str] | int | list[int] | None = None,
    title: str | None = None,
    **_,
) -> dict[str, Any]:
    """POST to a Home Assistant service.

    ``service`` defaults to ``$NOTIFY_TELEGRAM_SERVICE`` (fallback
    ``notify.telegram``). Common choices:

    * ``notify.<name>``  — HA notify integrations (persistent_notification,
      alexa_media_*, mobile_app_*, …). Body: ``{message, title?, target?}``.
    * ``telegram_bot.send_message`` — the direct Telegram-integration
      service. Body: ``{message, title?, target?}`` where ``target`` is
      the chat_id (int) — comes from ``$NOTIFY_TELEGRAM_TARGET`` when
      not passed per-action.
    """
    ha_url = os.getenv("HA_URL", "").rstrip("/")
    ha_token = os.getenv("HA_TOKEN")
    if not ha_url or not ha_token:
        return {
            "ok": False,
            "detail": "HA_URL + HA_TOKEN not set in backend/.env",
        }
    service = service or os.getenv("NOTIFY_TELEGRAM_SERVICE", "notify.telegram")
    domain, _, name = service.partition(".")
    if not domain or not name:
        return {"ok": False, "detail": f"invalid service: {service!r}"}

    if target is None:
        env_target = os.getenv("NOTIFY_TELEGRAM_TARGET")
        if env_target:
            # Comma-separated → list; single value → int if numeric
            if "," in env_target:
                target = [
                    int(t) if t.strip().lstrip("-").isdigit() else t.strip()
                    for t in env_target.split(",")
                ]
            elif env_target.lstrip("-").isdigit():
                target = int(env_target)
            else:
                target = env_target

    body: dict[str, Any] = {"message": text}
    if title:
        body["title"] = title
    if target is not None:
        body["target"] = target

    url = f"{ha_url}/api/services/{domain}/{name}"
    headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                url, json=body, headers=headers, timeout=15,
            ) as r:
                text_resp = await r.text()
                if r.status >= 400:
                    return {
                        "ok": False,
                        "detail": f"HA {r.status}: {text_resp[:200]}",
                    }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"{exc.__class__.__name__}: {exc}"}
    return {"ok": True, "detail": f"HA {service} ok"}


async def _log_only(text: str, **_) -> dict[str, Any]:
    log.info("notify (log-only): %s", text)
    return {"ok": True, "detail": "logged"}


CHANNELS = {
    "tts": _tts,
    "telegram": _telegram,
    "log": _log_only,
}


async def dispatch(action: dict[str, Any], default_text: str = "") -> dict[str, Any]:
    """Fire one notification action.

    Action shape:
        {"type": "tts",       "text": "..."}
        {"type": "telegram",  "text": "...", "title": "...", "target": "..."}

    ``text`` falls back to ``default_text`` (the rule's rendered
    message).
    """
    channel = str(action.get("type") or "").lower()
    fn = CHANNELS.get(channel)
    if fn is None:
        return {
            "ok": False,
            "detail": f"unknown channel {channel!r}; known: {sorted(CHANNELS)}",
        }
    text = str(action.get("text") or default_text or "").strip()
    if not text:
        return {"ok": False, "detail": "empty text"}
    # Pass any extra kwargs through (title, target, service, etc.)
    kwargs = {k: v for k, v in action.items() if k not in ("type", "text")}
    return await fn(text, **kwargs)


async def dispatch_all(
    actions: list[dict[str, Any]], default_text: str = "",
) -> list[dict[str, Any]]:
    out = []
    for a in actions or []:
        r = await dispatch(a, default_text=default_text)
        r = {**r, "channel": a.get("type")}
        out.append(r)
    return out
