"""Widget base class — every widget is a subclass that wires up its own
``fetch`` and declares its metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WidgetState:
    """Cached state for a widget — what the knowledge store holds."""

    fetched_at: float | None
    data: Any
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Widget:
    """Subclass and set the class attributes; override ``fetch``.

    The metadata is the "knowledge store" surface — it's what an LLM sees
    when it introspects the widget over MCP. Keep ``description`` and
    ``data_schema`` honest; they're the entire contract.
    """

    id: str = ""
    kind: str = ""
    name: str = ""
    description: str = ""
    refresh_seconds: int = 3600
    # Default tab + position for layout. Users can override via per-widget
    # config; the UI groups by ``tab`` and orders within a tab by ``position``.
    default_tab: str = "Local"
    default_position: int = 100
    # Widget default column/row span. Users can override via the
    # widget-header size popover, which writes to the layout row.
    default_width: int = 1
    default_height: int = 1
    # JSON-schema-ish hint of what ``data`` looks like — informational only,
    # not validated. Helps the LLM know what fields to ask about.
    data_schema: dict[str, Any] = {}
    # JSON-schema-ish hint of what user-tunable config keys exist.
    config_schema: dict[str, Any] = {}
    # Defaults used when no config row exists yet.
    default_config: dict[str, Any] = {}
    # Sheets backing (opt-in). When these are set AND a SheetsSync is
    # configured in main.py, the widget stores its list-of-items in a
    # Google Sheets tab instead of widget_config.
    sheets_tab: str = ""              # workbook tab name
    sheets_list_field: str = ""       # config field that holds the array
    sheets_field_order: list[str] = []  # widget field names in column order
    # HA integration surface — describes which config keys hold HA
    # ``entity_id`` strings so the Settings → HA Integrations tab can
    # list them and let the user swap the entity. Each entry:
    #   {"key": "ha_entity_id", "label": "Water depth sensor",
    #    "domain": "sensor", "required": True}
    # Widgets with a variable-length HA entity list (e.g. solar_vitals'
    # smart_ac rooms) can override ``ha_entities_for(config)``.
    ha_entities: list[dict[str, Any]] = []

    def ha_entities_for(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the list of HA-entity config keys for the current
        config. Default: return the static ``ha_entities`` list with
        each entry's ``entity_id`` filled from the config."""
        out = []
        for e in self.ha_entities:
            out.append({
                **e,
                "entity_id": config.get(e["key"]) or e.get("default") or "",
            })
        return out

    def meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "refresh_seconds": self.refresh_seconds,
            "default_tab": self.default_tab,
            "default_position": self.default_position,
            "sheets_tab": self.sheets_tab,
            "sheets_list_field": self.sheets_list_field,
            "data_schema": self.data_schema,
            "config_schema": self.config_schema,
            "default_config": self.default_config,
        }

    async def fetch(self, config: dict[str, Any]) -> Any:
        """Pull fresh data from the source. Return JSON-serialisable data.

        Raise on failure; the refresher will record the error in state.
        """
        raise NotImplementedError
