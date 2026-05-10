"""Vendor-specific solar monitoring adapters.

Each adapter implements the SiteAdapter contract: login + the same five data
methods the EG4 path always had. Sites in the DB carry a `vendor` column that
this package uses to pick the right adapter class.
"""

from __future__ import annotations

import json
from typing import Any

from .base import Inverter, SiteAdapter
from .eg4 import EG4Adapter
from .qcell import QCellAdapter
from .solaredge import SolarEdgeAdapter

ADAPTERS: dict[str, type[SiteAdapter]] = {
    "eg4": EG4Adapter,
    "solaredge": SolarEdgeAdapter,
    "qcell": QCellAdapter,
}


def build_adapter(site_row: dict[str, Any]) -> SiteAdapter:
    """Construct an adapter from a sites table row."""
    vendor = site_row["vendor"]
    cls = ADAPTERS.get(vendor)
    if cls is None:
        raise ValueError(f"unknown vendor: {vendor}")
    creds = site_row.get("credentials_json") or "{}"
    if isinstance(creds, str):
        creds = json.loads(creds)
    config = site_row.get("config_json") or "{}"
    if isinstance(config, str):
        config = json.loads(config)
    return cls(site_id=site_row["id"], credentials=creds, config=config)


__all__ = ["SiteAdapter", "Inverter", "build_adapter", "ADAPTERS"]
