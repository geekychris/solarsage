"""Google Sheets client for widget list persistence.

The user shares a single "SolarSage Lists" workbook with a service
account. Each Sheets-backed widget declares:

    sheets_tab         = "Contacts"
    sheets_list_field  = "contacts"            # widget config field
    sheets_field_order = ["name", "phone", "email", "location",
                          "tags", "notes"]

When ``SOLARSAGE_SHEET_ID`` + ``GOOGLE_APPLICATION_CREDENTIALS`` env
vars are set, the widget's fetch() reads from Sheets, and PUT config
writes back. Otherwise the widget falls back to SQLite widget_config
transparently — nothing breaks for anyone who skips the setup.

gspread is synchronous; we run its calls in a thread pool so the
FastAPI event loop stays free.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

log = logging.getLogger("eg4.sheets")


_TRUE = {"true", "yes", "1", "y", "t"}


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in _TRUE


def _from_cell(v: Any, field: str) -> Any:
    """Normalize a cell value into the shape widgets expect.

    * ``tags``, ``labels`` etc. — split comma/space to list
    * ``checked``, ``done``, boolean-ish fields — parse truthy strings
      (None → False so widgets can rely on the value being a bool)
    * ``wait_min``, ``priority``, numeric fields — coerce to int when they parse
    """
    if field in ("checked", "done", "starred"):
        return _to_bool(v)
    if v is None:
        return None
    if field in ("tags",):
        s = str(v).strip()
        if not s:
            return []
        return [t.strip() for t in s.replace(";", ",").split(",") if t.strip()]
    if field in ("wait_min", "priority", "position", "kwh"):
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            try:
                return float(str(v).strip())
            except (ValueError, TypeError):
                return None
    return v


def _to_cell(v: Any) -> Any:
    """Serialize a widget value back to a cell string."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return v


def _col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class SheetsSync:
    """Wraps a single workbook. All gspread work runs off the event loop."""

    def __init__(self, creds_path: str, sheet_id: str) -> None:
        # Delayed import so a Pi without gspread still boots
        import gspread
        from google.oauth2 import service_account

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=scopes,
        )
        client = gspread.authorize(creds)
        self._sheet = client.open_by_key(sheet_id)
        self._tabs: dict[str, Any] = {
            ws.title: ws for ws in self._sheet.worksheets()
        }
        self._sheet_id = sheet_id
        log.info(
            "sheets connected: id=%s… tabs=%s",
            sheet_id[:10], sorted(self._tabs),
        )

    def _tab(self, tab_name: str):
        ws = self._tabs.get(tab_name)
        if ws is None:
            # Refresh once in case the user added a tab after startup
            self._tabs = {ws.title: ws for ws in self._sheet.worksheets()}
            ws = self._tabs.get(tab_name)
        if ws is None:
            raise ValueError(
                f"tab {tab_name!r} not found in sheet "
                f"(available: {sorted(self._tabs)})"
            )
        return ws

    def _ensure_tab_sync(
        self, tab_name: str, field_order: list[str],
    ) -> Any:
        """Create the tab + write the header row if it doesn't exist."""
        try:
            return self._tab(tab_name)
        except ValueError:
            pass
        ncols = max(6, len(field_order))
        ws = self._sheet.add_worksheet(title=tab_name, rows=200, cols=ncols)
        if field_order:
            ws.update(values=[field_order], range_name="A1")
        self._tabs[tab_name] = ws
        log.info("sheets: created missing tab %r with headers %s",
                 tab_name, field_order)
        return ws

    async def ensure_tab(
        self, tab_name: str, field_order: list[str],
    ) -> None:
        await asyncio.to_thread(self._ensure_tab_sync, tab_name, field_order)

    # --- read ---------------------------------------------------------

    def _read_sync(
        self, tab: str, field_order: list[str],
    ) -> list[dict[str, Any]]:
        ws = self._tab(tab)
        # get_all_values gives every row as a list of strings
        rows = ws.get_all_values()
        if not rows:
            return []
        header = [h.strip().lower() for h in rows[0]]
        out: list[dict[str, Any]] = []
        for row in rows[1:]:
            if not any(cell.strip() for cell in row):
                continue
            record: dict[str, Any] = {}
            for i, cell in enumerate(row):
                key = header[i] if i < len(header) else None
                if not key:
                    continue
                if key in field_order:
                    record[key] = _from_cell(cell, key)
                else:
                    # Preserve unknown columns as strings so the user
                    # can add ad-hoc notes without losing them.
                    record[key] = cell
            # Ensure every widget field has a key even if the column
            # is missing / empty, so the frontend doesn't crash.
            for f in field_order:
                record.setdefault(f, "" if f in ("name", "text", "label") else None)
            out.append(record)
        return out

    async def read(
        self, tab: str, field_order: list[str],
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._read_sync, tab, field_order)

    # --- write --------------------------------------------------------

    def _write_sync(
        self, tab: str, field_order: list[str], items: list[dict[str, Any]],
    ) -> None:
        ws = self._ensure_tab_sync(tab, field_order)
        headers = [h.strip() for h in ws.row_values(1)]
        if not headers:
            # Populate header row on first write
            ws.update(values=[field_order], range_name="A1")
            headers = field_order

        # Wipe everything from row 2 down (avoid leaving stale rows)
        end_col = _col_letter(max(len(headers), len(field_order)))
        try:
            ws.batch_clear([f"A2:{end_col}"])
        except Exception:
            pass

        rows_out = []
        headers_lc = [h.lower() for h in headers]
        for item in items:
            row = []
            for col in headers_lc:
                if col in item:
                    row.append(_to_cell(item.get(col)))
                elif col in field_order and col in item:
                    row.append(_to_cell(item[col]))
                else:
                    row.append(_to_cell(item.get(col, "")))
            rows_out.append(row)

        if rows_out:
            ws.update(
                f"A2:{end_col}{1 + len(rows_out)}",
                rows_out,
                value_input_option="USER_ENTERED",
            )

    async def write(
        self, tab: str, field_order: list[str],
        items: list[dict[str, Any]],
    ) -> None:
        await asyncio.to_thread(self._write_sync, tab, field_order, items)

    # --- append (long-term retention) --------------------------------

    def _append_rows_sync(
        self, tab: str, field_order: list[str],
        items: list[dict[str, Any]],
    ) -> int:
        """Append ``items`` after the last non-empty row. Never truncates
        prior rows — safe for indefinite-retention logs."""
        if not items:
            return 0
        ws = self._ensure_tab_sync(tab, field_order)
        headers = [h.strip() for h in ws.row_values(1)]
        if not headers:
            ws.update(values=[field_order], range_name="A1")
            headers = field_order
        headers_lc = [h.lower() for h in headers]
        rows_out = []
        for item in items:
            row = [_to_cell(item.get(col, "")) for col in headers_lc]
            rows_out.append(row)
        ws.append_rows(rows_out, value_input_option="USER_ENTERED")
        return len(rows_out)

    async def append_rows(
        self, tab: str, field_order: list[str],
        items: list[dict[str, Any]],
    ) -> int:
        return await asyncio.to_thread(
            self._append_rows_sync, tab, field_order, items,
        )

    def _list_column_sync(self, tab: str, column: str) -> list[str]:
        """Return the string values of one column (below the header row).
        Returns [] if the tab or column doesn't exist."""
        try:
            ws = self._tab(tab)
        except ValueError:
            return []
        headers = [h.strip().lower() for h in ws.row_values(1)]
        col_lc = column.strip().lower()
        if col_lc not in headers:
            return []
        col_idx = headers.index(col_lc) + 1  # gspread is 1-indexed
        col_vals = ws.col_values(col_idx)
        return [v for v in col_vals[1:] if v]

    async def list_column(self, tab: str, column: str) -> list[str]:
        return await asyncio.to_thread(self._list_column_sync, tab, column)


def load_sheets_from_env() -> SheetsSync | None:
    """Return an initialized SheetsSync when the env has both a key path
    and a sheet id. Log + return None on any misconfiguration; the
    widgets fall back to SQLite.
    """
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    sheet_id = os.getenv("SOLARSAGE_SHEET_ID")
    if not key_path or not sheet_id:
        return None
    if not os.path.exists(key_path):
        log.warning(
            "GOOGLE_APPLICATION_CREDENTIALS points to a file that "
            "doesn't exist: %s", key_path,
        )
        return None
    try:
        return SheetsSync(key_path, sheet_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("sheets init failed: %s", exc)
        return None
