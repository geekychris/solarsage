"""Projects widget — multi-item projects with cost + assignee.

Hierarchy:

* ``projects[]``  — project-level metadata (name, assignee, description,
                    target date, done, notes). Edited from the dashboard.
* ``items[]``     — flat task list; each item names its parent project.
                    Synced to the "Projects" tab of your SolarSage
                    workbook so you can bulk-edit costs and check off
                    tasks from the Google Sheets app.

Per-task ``assignee`` and ``due`` are optional. When blank, the widget
falls back to the parent project's values on display and in rollup
stats. That way "Juan is doing the whole deck" is one entry on the
project instead of copying into every task.

Adding a task in Sheets to a project name that doesn't have a
metadata entry yet just-in-time creates one with empty metadata — so
editing entirely from Sheets stays valid.
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


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


class ProjectsWidget(Widget):
    id = "projects"
    kind = "projects"
    name = "Projects"
    description = (
        "Multi-task projects with cost, assignee, and target date. "
        "Create a project (with its own who / when), then add tasks "
        "underneath. Task assignee and due date inherit from the "
        "project when blank. Tasks sync to the Projects tab of your "
        "SolarSage Lists workbook; project-level metadata lives on "
        "the dashboard."
    )
    refresh_seconds = 6 * 3600
    default_tab = "Lists"
    default_position = 32   # right after Todo (30)

    # Only tasks live in Sheets; project metadata is dashboard-only
    # (see the module docstring for the rationale).
    sheets_tab = "Projects"
    sheets_list_field = "items"
    sheets_field_order = [
        "project", "text", "cost",
        "assignee", "due", "done", "notes",
    ]

    config_schema = {
        "type": "object",
        "properties": {
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name":        {"type": "string"},
                        "description": {"type": "string"},
                        "assignee":    {"type": "string"},
                        "due":         {"type": ["string", "null"],
                                        "format": "date"},
                        "done":        {"type": "boolean"},
                        "notes":       {"type": "string"},
                    },
                },
            },
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
    default_config = {"projects": [], "items": []}

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        # Normalize projects[] into an ordered dict keyed by name.
        proj_map: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        for p in list(config.get("projects") or []):
            if not isinstance(p, dict):
                continue
            name = _str(p.get("name"))
            if not name:
                continue
            proj_map[name] = {
                "name":        name,
                "description": _str(p.get("description")),
                "assignee":    _str(p.get("assignee")),
                "due":         _str(p.get("due")) or None,
                "done":        bool(p.get("done")),
                "notes":       _str(p.get("notes")),
            }

        # Normalize tasks.
        items: list[dict[str, Any]] = []
        for it in list(config.get("items") or []):
            if not isinstance(it, dict):
                continue
            project = _str(it.get("project"))
            text = _str(it.get("text"))
            if not project or not text:
                continue
            items.append({
                "project":  project,
                "text":     text,
                "cost":     _num(it.get("cost")),
                "assignee": _str(it.get("assignee")),
                "due":      _str(it.get("due")) or None,
                "done":     bool(it.get("done")),
                "notes":    _str(it.get("notes")),
            })

        # JIT-create empty project metadata for tasks whose project has
        # no explicit entry yet (typical after adding rows from Sheets).
        for it in items:
            if it["project"] not in proj_map:
                proj_map[it["project"]] = {
                    "name": it["project"],
                    "description": "",
                    "assignee": "",
                    "due": None,
                    "done": False,
                    "notes": "",
                }

        # Roll up.
        today = date.today().isoformat()
        buckets: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        for name, meta in proj_map.items():
            buckets[name] = {
                **meta,
                "items": [],
                "total_cost": 0.0,
                "done_cost": 0.0,
                "item_count": 0,
                "done_count": 0,
                "overdue_count": 0,
                "next_due": None,
                "assignees": [meta["assignee"]] if meta["assignee"] else [],
            }
        for it in items:
            b = buckets[it["project"]]
            # Effective values inherit from the project when blank.
            eff_assignee = it["assignee"] or b["assignee"]
            eff_due = it["due"] or b["due"]
            it_out = {
                **it,
                "effective_assignee": eff_assignee,
                "effective_due":      eff_due,
                "inherited_assignee": bool(not it["assignee"] and b["assignee"]),
                "inherited_due":      bool(not it["due"] and b["due"]),
            }
            b["items"].append(it_out)
            b["item_count"] += 1
            if it["cost"] is not None:
                b["total_cost"] += it["cost"]
                if it["done"]:
                    b["done_cost"] += it["cost"]
            if it["done"]:
                b["done_count"] += 1
            if eff_due and not it["done"] and eff_due < today:
                b["overdue_count"] += 1
            if eff_due and not it["done"]:
                cur = b["next_due"]
                if cur is None or eff_due < cur:
                    b["next_due"] = eff_due
            if eff_assignee and eff_assignee not in b["assignees"]:
                b["assignees"].append(eff_assignee)

        # Finalize + serialize.
        projects_out = []
        for b in buckets.values():
            b["total_cost"] = round(b["total_cost"], 2)
            b["done_cost"] = round(b["done_cost"], 2)
            b["open_count"] = b["item_count"] - b["done_count"]
            b["all_done"] = (
                b["item_count"] > 0 and b["done_count"] == b["item_count"]
            )
            projects_out.append(b)

        stats = {
            "project_count":     len(projects_out),
            "open_project_count": sum(
                1 for p in projects_out
                if not p["done"] and not p["all_done"]
            ),
            "item_count":  len(items),
            "open_count":  sum(1 for it in items if not it["done"]),
            "overdue_count": sum(
                1 for it in items
                if (it["due"] or proj_map[it["project"]]["due"])
                and not it["done"]
                and (it["due"] or proj_map[it["project"]]["due"]) < today
            ),
            "total_cost": round(sum((it["cost"] or 0.0) for it in items), 2),
            "done_cost":  round(
                sum((it["cost"] or 0.0) for it in items if it["done"]), 2,
            ),
        }

        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "projects": projects_out,
            "items": items,
            "stats": stats,
        }
