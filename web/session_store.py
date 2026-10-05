"""Session + temp-file storage for the web service.

Each browser session gets an isolated folder:
    <data>/sessions/<32-hex-id>/<file-id>.pdf ...

Old sessions are swept on creation (multiprocess-safe, no threads).
All ids are strict 32-hex so paths can never traverse.
"""
from __future__ import annotations

import os
import re
import shutil
import time
import uuid

HEX32 = re.compile(r"^[0-9a-f]{32}$")


def data_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.environ.get("WEB_DATA_DIR", os.path.join(here, "data"))
    os.makedirs(root, exist_ok=True)
    return root


def sessions_root() -> str:
    root = os.path.join(data_root(), "sessions")
    os.makedirs(root, exist_ok=True)
    return root


def _check_id(value: str, name: str = "id") -> str:
    if not isinstance(value, str) or not HEX32.match(value):
        raise ValueError(f"Invalid {name}.")
    return value


def new_session(ttl_hours: float = 6.0) -> str:
    sweep_old(ttl_hours)
    sid = uuid.uuid4().hex
    os.makedirs(os.path.join(sessions_root(), sid), exist_ok=True)
    return sid


def session_dir(sid: str) -> str:
    _check_id(sid, "session_id")
    path = os.path.join(sessions_root(), sid)
    if not os.path.isdir(path):
        raise ValueError("Session expired or unknown. Reload the page.")
    return path


def delete_session(sid: str) -> None:
    try:
        shutil.rmtree(os.path.join(sessions_root(), _check_id(sid)), ignore_errors=True)
    except ValueError:
        pass


def session_files_size(sid: str) -> int:
    total = 0
    try:
        for name in os.listdir(session_dir(sid)):
            if name.endswith(".pdf"):
                total += os.path.getsize(os.path.join(session_dir(sid), name))
    except (ValueError, OSError):
        pass
    return total


def new_file_id() -> str:
    return uuid.uuid4().hex


def file_path(sid: str, fid: str) -> str:
    return os.path.join(session_dir(sid), _check_id(fid, "file_id") + ".pdf")


def sweep_old(ttl_hours: float = 6.0) -> int:
    """Delete session folders older than TTL. Returns count removed."""
    removed = 0
    root = sessions_root()
    cutoff = time.time() - ttl_hours * 3600
    try:
        names = os.listdir(root)
    except OSError:
        return 0
    for name in names:
        if not HEX32.match(name):
            continue
        path = os.path.join(root, name)
        try:
            if os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return removed
