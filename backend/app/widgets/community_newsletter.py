"""HOA newsletter card.

Reads the HOA widget's cached state and surfaces just the latest
newsletter PDF link (plus any other PDFs that mention "newsletter" in
their label). Saves the user from scanning the full HOA scrape just to
find the newsletter.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .base import Widget


NEWSLETTER_RE = re.compile(r"news\s*letter", re.IGNORECASE)


class NewsletterWidget(Widget):
    id = "hoa_newsletter"
    kind = "hoa_newsletter"
    name = "HOA newsletter"
    description = (
        "Latest HOA newsletter PDF. Pulled from the same scrape as the "
        "HOA activities widget; this card just isolates the newsletter "
        "links so they're one click away."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Community"
    default_position = 60

    # Doesn't talk to the network directly — reads the cached HOA widget
    # state out of the same SQLite store. The store path comes from the
    # config so we can test the widget standalone.
    config_schema = {
        "type": "object",
        "properties": {"source_widget_id": {"type": "string"}},
    }
    default_config = {"source_widget_id": "hoa"}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        # Local import avoids a circular dependency at module load time.
        from . import registry as _registry_mod
        from .store import WidgetStore
        import os

        source_id = str(config.get("source_widget_id", "hoa"))
        db_path = os.getenv("EG4_DB_PATH", "./eg4_history.db")
        store = WidgetStore(db_path)
        state = await store.get_state(source_id)
        if not state or not state.data:
            return {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source_widget_id": source_id,
                "newsletters": [],
                "note": (
                    f"source widget '{source_id}' has no cached data yet; "
                    "this widget will populate once the HOA scrape runs."
                ),
            }
        all_pdfs = state.data.get("all_pdfs") or []
        newsletters = [p for p in all_pdfs if NEWSLETTER_RE.search(p.get("label", ""))]
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_widget_id": source_id,
            "latest": newsletters[0] if newsletters else None,
            "newsletters": newsletters,
        }
