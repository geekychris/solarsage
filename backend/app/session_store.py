"""In-memory session store for SolarSage.

Two layers:

  * `Session` (legacy, EG4 UI auth): bearer token → username + EG4InverterAPI
    client. Created on UI login; used by the dashboard.
  * `SiteSession`: per-site adapter session keyed by site_id. Lives for the
    lifetime of the backend process; auto-refreshed by the poller on failure.

The two will be unified eventually — for now the legacy bearer auth still
points at an EG4InverterAPI instance because the UI dashboard reads its
properties directly. New code uses SiteSession via the adapter pattern.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from eg4_inverter_api import EG4InverterAPI

from .adapters import SiteAdapter


@dataclass
class Session:
    token: str
    username: str
    client: EG4InverterAPI
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created_at: float = field(default_factory=time.time)
    poller_task: Optional[asyncio.Task] = None


@dataclass
class SiteSession:
    site_id: str
    adapter: SiteAdapter
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    poller_task: Optional[asyncio.Task] = None
    last_error: Optional[str] = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._site_sessions: dict[str, SiteSession] = {}

    # ---- legacy UI sessions ----
    def create(self, username: str, client: EG4InverterAPI) -> Session:
        token = secrets.token_urlsafe(32)
        session = Session(token=token, username=username, client=client)
        self._sessions[token] = session
        return session

    def get(self, token: str) -> Optional[Session]:
        return self._sessions.get(token)

    async def drop(self, token: str) -> None:
        session = self._sessions.pop(token, None)
        if session is None:
            return
        if session.poller_task is not None:
            session.poller_task.cancel()
        await session.client.close()

    async def drop_all(self) -> None:
        for token in list(self._sessions.keys()):
            await self.drop(token)
        for sid in list(self._site_sessions.keys()):
            await self.drop_site(sid)

    # ---- site sessions ----
    def set_site(self, ss: SiteSession) -> None:
        self._site_sessions[ss.site_id] = ss

    def get_site(self, site_id: str) -> Optional[SiteSession]:
        return self._site_sessions.get(site_id)

    def all_sites(self) -> list[SiteSession]:
        return list(self._site_sessions.values())

    async def drop_site(self, site_id: str) -> None:
        ss = self._site_sessions.pop(site_id, None)
        if ss is None:
            return
        if ss.poller_task is not None:
            ss.poller_task.cancel()
        try:
            await ss.adapter.close()
        except Exception:
            pass
