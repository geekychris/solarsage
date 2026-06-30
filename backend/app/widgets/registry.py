"""Global widget registry. Populated at startup from main.py."""

from __future__ import annotations

from typing import Iterable

from .base import Widget


class WidgetRegistry:
    def __init__(self) -> None:
        self._widgets: dict[str, Widget] = {}

    def register(self, widget: Widget) -> None:
        if not widget.id:
            raise ValueError(f"widget {widget.__class__.__name__} has empty id")
        if widget.id in self._widgets:
            raise ValueError(f"duplicate widget id: {widget.id}")
        self._widgets[widget.id] = widget

    def get(self, widget_id: str) -> Widget | None:
        return self._widgets.get(widget_id)

    def all(self) -> Iterable[Widget]:
        return self._widgets.values()


registry = WidgetRegistry()
