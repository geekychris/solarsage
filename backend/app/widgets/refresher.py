"""Background refresher — one asyncio task per widget."""

from __future__ import annotations

import asyncio
import logging
import time

from .base import Widget
from .registry import WidgetRegistry
from .store import WidgetStore

log = logging.getLogger("eg4.widgets")


async def _refresh_once(widget: Widget, store: WidgetStore) -> None:
    config = await store.get_config(widget.id)
    if config is None:
        config = dict(widget.default_config)
    try:
        data = await widget.fetch(config)
        await store.record_success(widget.id, data)
        log.info("widget %s refreshed", widget.id)
    except Exception as exc:  # noqa: BLE001 — surface anything to the store
        log.warning("widget %s refresh failed: %s", widget.id, exc)
        await store.record_error(widget.id, f"{exc.__class__.__name__}: {exc}")


async def _widget_loop(widget: Widget, store: WidgetStore) -> None:
    # First fetch is immediate but offset slightly so several widgets don't
    # all hit external APIs simultaneously at boot.
    await asyncio.sleep(1)
    while True:
        await _refresh_once(widget, store)
        await asyncio.sleep(max(60, widget.refresh_seconds))


async def run_widget_refreshers(registry: WidgetRegistry, store: WidgetStore) -> None:
    """Top-level task: run one refresh loop per registered widget concurrently."""
    tasks = [
        asyncio.create_task(_widget_loop(w, store), name=f"widget:{w.id}")
        for w in registry.all()
    ]
    if not tasks:
        return
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        raise


async def refresh_now(widget: Widget, store: WidgetStore) -> None:
    """Force an immediate refresh — used by the POST /api/widgets/{id}/refresh
    endpoint so a user can pull fresh data without waiting for the loop."""
    await _refresh_once(widget, store)
