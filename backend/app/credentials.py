"""Local-only credential file.

Plain-JSON on disk with mode 0600. This is the same security posture as
storing creds in .env — both work because the app runs locally for a single
user. Do not deploy on a shared host. The file is also in .gitignore.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional


def _path() -> Path:
    return Path(os.getenv("EG4_CREDS_PATH", "./credentials.json"))


def load() -> Optional[tuple[str, str]]:
    p = _path()
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    u, pw = d.get("username"), d.get("password")
    if not u or not pw:
        return None
    return u, pw


def save(username: str, password: str) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"username": username, "password": password}))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — owner read/write only
    os.replace(tmp, p)


def clear() -> bool:
    p = _path()
    if p.exists():
        p.unlink()
        return True
    return False


def exists() -> bool:
    return _path().exists()
