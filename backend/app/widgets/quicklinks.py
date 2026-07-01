"""Quick-links widget — purely client-configured bookmarks.

No external fetching; ``fetch`` just echoes the config back so the
frontend can render a curated list of useful URLs (HOA login, Pemex
price page, CFE outage map, bank, weather radar, etc.).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import Widget


class QuickLinksWidget(Widget):
    id = "quicklinks"
    kind = "quicklinks"
    name = "Quick links"
    description = (
        "Curated bookmarks for the things you reach for daily — HOA "
        "login, Pemex price page, CFE outage map, banks. Edit via "
        "Settings to add your own."
    )
    refresh_seconds = 24 * 3600
    default_tab = "Community"
    default_position = 80
    sheets_tab = "Bookmarks"
    sheets_list_field = "links"
    sheets_field_order = ["label", "url", "group"]

    config_schema = {
        "type": "object",
        "properties": {
            "links": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["label", "url"],
                    "properties": {
                        "label": {"type": "string"},
                        "url":   {"type": "string", "format": "uri"},
                        "group": {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {
        "links": [
            {"group": "HOA",      "label": "El Dorado Ranch HOA",
             "url": "https://www.eldoradoranchhoa.com.mx/"},
            {"group": "Utilities", "label": "CFE outage map",
             "url": "https://app.cfe.mx/Aplicaciones/CCFE/InterrupcionesPorEstado/"},
            {"group": "Fuel",     "label": "Pemex prices (Mx open data)",
             "url": "https://datos.gob.mx/busca/dataset/precios-vigentes-de-gasolinas-y-diesel"},
            {"group": "Border",   "label": "CBP Border Wait Times",
             "url": "https://bwt.cbp.gov/"},
            {"group": "Weather",  "label": "NHC Eastern Pacific outlook",
             "url": "https://www.nhc.noaa.gov/text/MIATWOEP.shtml"},
            {"group": "Bank",     "label": "Banxico FX fixings",
             "url": "https://www.banxico.org.mx/tipcamb/tipCamMIAction.do"},
        ]
    }

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        # No network — just return whatever the user configured.
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "links": config.get("links") or [],
        }
