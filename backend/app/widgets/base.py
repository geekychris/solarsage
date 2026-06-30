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
    # JSON-schema-ish hint of what ``data`` looks like — informational only,
    # not validated. Helps the LLM know what fields to ask about.
    data_schema: dict[str, Any] = {}
    # JSON-schema-ish hint of what user-tunable config keys exist.
    config_schema: dict[str, Any] = {}
    # Defaults used when no config row exists yet.
    default_config: dict[str, Any] = {}

    def meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "refresh_seconds": self.refresh_seconds,
            "data_schema": self.data_schema,
            "config_schema": self.config_schema,
            "default_config": self.default_config,
        }

    async def fetch(self, config: dict[str, Any]) -> Any:
        """Pull fresh data from the source. Return JSON-serialisable data.

        Raise on failure; the refresher will record the error in state.
        """
        raise NotImplementedError
