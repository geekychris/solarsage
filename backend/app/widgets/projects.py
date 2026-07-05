"""Projects widget — multi-item tasks with cost + assignee.

Todo-style but richer: each item belongs to a named project (grouping
key), and carries an optional cost, assignee, and due date on top of
the usual done/notes fields. The widget rolls items up by project so
the dashboard can show "Rear patio deck — 3 items, $800 committed, 1
done" at a glance.

Sheets-backed (tab: ``Projects``). Each row = one line item, with the
project name repeating in column A. That makes editing from the Google
Sheets app trivial — add a row to a project by copying an existing row
and changing text/cost.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Any

from .base import Widget


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ProjectsWidget(Widget):
    id = "projects"
    kind = "projects"
    name = "Projects"
    description = (
        "Multi-item projects with cost and assignee per task — like Todo "
        "but for renovations, maintenance, and anything with sub-tasks. "
        "Rolls up total + committed cost per project. Syncs to the "
        "Projects tab of your SolarSage Lists workbook."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Lists"
    default_position = 32   # right after Todo (30)

    sheets_tab = "Projects"
    sheets_list_field = "items"
    sheets_field_order = [
        "project", "text", "cost",
        "assignee", "due", "done", "notes",
    ]

    config_schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["project", "text"],
                    "properties": {
                        "project":  {"type": "string"},
                        "text":     {"type": "string"},
                        "cost":     {"type": ["number", "null"]},
                        "assignee": {"type": "string"},
                        "due":      {"type": ["string", "null"],
                                     "format": "date"},
                        "done":     {"type": "boolean"},
                        "notes":    {"type": "string"},
                    },
                },
            },
        },
    }
    default_config = {"items": []}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        raw_items = list(config.get("items") or [])
        # Normalize a bit — Sheets can send costs as strings, done as "TRUE"
        items: list[dict[str, Any]] = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            project = str(it.get("project") or "").strip()
            text = str(it.get("text") or "").strip()
            if not project or not text:
                continue
            items.append({
                "project":  project,
                "text":     text,
                "cost":     _num(it.get("cost")),
                "assignee": str(it.get("assignee") or "").strip(),
                "due":      str(it.get("due") or "").strip() or None,
                "done":     bool(it.get("done")),
                "notes":    str(it.get("notes") or "").strip(),
            })

        # Roll up per project, preserving insertion order.
        today = date.today().isoformat()
        buckets: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        for it in items:
            b = buckets.setdefault(it["project"], {
                "project": it["project"],
                "items": [],
                "total_cost": 0.0,
                "done_cost": 0.0,
                "item_count": 0,
                "done_count": 0,
                "overdue_count": 0,
                "next_due": None,
                "assignees": [],
            })
            b["items"].append(it)
            b["item_count"] += 1
            if it["cost"] is not None:
                b["total_cost"] += it["cost"]
                if it["done"]:
                    b["done_cost"] += it["cost"]
            if it["done"]:
                b["done_count"] += 1
            if it["due"] and not it["done"] and it["due"] < today:
                b["overdue_count"] += 1
            if it["due"] and not it["done"]:
                cur = b["next_due"]
                if cur is None or it["due"] < cur:
                    b["next_due"] = it["due"]
            if it["assignee"] and it["assignee"] not in b["assignees"]:
                b["assignees"].append(it["assignee"])

        projects = []
        for b in buckets.values():
            b["total_cost"] = round(b["total_cost"], 2)
            b["done_cost"] = round(b["done_cost"], 2)
            b["open_count"] = b["item_count"] - b["done_count"]
            b["all_done"] = b["done_count"] == b["item_count"] and b["item_count"] > 0
            projects.append(b)

        stats = {
            "project_count": len(projects),
            "item_count": len(items),
            "open_count": sum(1 for it in items if not it["done"]),
            "overdue_count": sum(
                1 for it in items
                if it["due"] and not it["done"] and it["due"] < today
            ),
            "total_cost": round(
                sum((it["cost"] or 0.0) for it in items), 2,
            ),
            "done_cost": round(
                sum((it["cost"] or 0.0) for it in items if it["done"]), 2,
            ),
        }

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "projects": projects,
            "stats": stats,
        }
