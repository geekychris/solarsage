"""Server-side widget registry.

A "widget" is a self-describing piece of dashboard data that:

* fetches from some external source (tide service, HOA page, CBP feed, …)
* caches its result in SQLite (the "knowledge store")
* publishes structured metadata so the REST / MCP layer can introspect it

The frontend renders a `Local` tab driven entirely by `/api/widgets`; the LLM
talks to the same data via the MCP tools in `mcp_server/server.py`.
"""

from .base import Widget, WidgetState
from .registry import WidgetRegistry, registry
from .store import WidgetStore
from .refresher import run_widget_refreshers

__all__ = [
    "Widget",
    "WidgetState",
    "WidgetRegistry",
    "WidgetStore",
    "registry",
    "run_widget_refreshers",
]
