"""Thin client for the local TTS HTTP service (tts_speaker.py on the Pi).

POST /say with ``{"text": "<utterance>"}`` → 200 OK once playback completes.
"""

from __future__ import annotations

import logging
import os

import aiohttp

log = logging.getLogger("eg4.events.tts")

TTS_URL = os.getenv("TTS_URL", "http://localhost:5006/say")


async def say(text: str) -> bool:
    """Best-effort speak. Returns True on 2xx. Never raises."""
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                TTS_URL, json={"text": text}, timeout=60,
            ) as r:
                if r.status >= 400:
                    body = (await r.text())[:200]
                    log.warning(
                        "TTS %s failed: HTTP %s — %s", TTS_URL, r.status, body
                    )
                    return False
                return True
    except Exception as exc:  # noqa: BLE001
        log.warning("TTS %s unreachable: %s", TTS_URL, exc)
        return False
