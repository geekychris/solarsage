"""Background refresher — one asyncio task per widget."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .base import Widget
from .registry import WidgetRegistry
from .store import WidgetStore

log = logging.getLogger("eg4.widgets")


async def _apply_sheets_read(
    widget: Widget, config: dict[str, Any], sheets: Any | None,
) -> dict[str, Any]:
    """When the widget is Sheets-backed AND a SheetsSync is configured,
    replace ``config[list_field]`` with the current Sheets rows.

    Falls through on failure (widget will use whatever config already
    holds — usually the last-known good SQLite copy or defaults)."""
    if sheets is None:
        return config
    if not widget.sheets_tab or not widget.sheets_list_field:
        return config
    try:
        rows = await sheets.read(widget.sheets_tab, widget.sheets_field_order)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "sheets read for %s tab=%r failed: %s",
            widget.id, widget.sheets_tab, exc,
        )
        return config
    return {**config, widget.sheets_list_field: rows}


async def _refresh_once(
    widget: Widget, store: WidgetStore, sheets: Any | None = None,
) -> None:
    try:
        config = await store.get_config(widget.id)
    except Exception as exc:  # noqa: BLE001
        log.warning("widget %s: get_config failed: %s", widget.id, exc)
        config = None
    if config is None:
        config = dict(widget.default_config)
    config = await _apply_sheets_read(widget, config, sheets)
    try:
        data = await widget.fetch(config)
    except Exception as exc:  # noqa: BLE001 — surface anything to the store
        log.warning("widget %s fetch failed: %s", widget.id, exc)
        try:
            await store.record_error(widget.id, f"{exc.__class__.__name__}: {exc}")
        except Exception as exc2:  # noqa: BLE001
            # Keep the loop alive even if the store itself is unhappy —
            # the next tick will retry.
            log.error("widget %s: record_error failed: %s", widget.id, exc2)
        return
    try:
        await store.record_success(widget.id, data)
        log.info("widget %s refreshed", widget.id)
    except Exception as exc:  # noqa: BLE001
        log.error("widget %s: record_success failed: %s", widget.id, exc)


async def _widget_loop(
    widget: Widget, store: WidgetStore, sheets: Any | None = None,
) -> None:
    # First fetch is immediate but offset slightly so several widgets don't
    # all hit external APIs simultaneously at boot.
    await asyncio.sleep(1)
    while True:
        await _refresh_once(widget, store, sheets)
        await asyncio.sleep(max(60, widget.refresh_seconds))


async def run_widget_refreshers(
    registry: WidgetRegistry, store: WidgetStore, sheets: Any | None = None,
) -> None:
    """Top-level task: run one refresh loop per registered widget concurrently."""
    tasks = [
        asyncio.create_task(_widget_loop(w, store, sheets), name=f"widget:{w.id}")
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


async def refresh_now(
    widget: Widget, store: WidgetStore, sheets: Any | None = None,
) -> None:
    """Force an immediate refresh — used by the POST /api/widgets/{id}/refresh
    endpoint so a user can pull fresh data without waiting for the loop."""
    await _refresh_once(widget, store, sheets)
