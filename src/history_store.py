"""Local history store (SQLite) — thesis enhancement (RM §6).

Keeps a local log of merges: timestamp, output path, inputs, page totals.
100% offline. Failure to log must never break a merge.
"""
from __future__ import annotations

import os
import sqlite3
import time

DB_NAME = "history.db"


def db_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, DB_NAME)


def init_db() -> None:
    try:
        con = sqlite3.connect(db_path())
        con.execute(
            """CREATE TABLE IF NOT EXISTS merges(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL, output TEXT, files INTEGER,
                pages INTEGER, detail TEXT)"""
        )
        con.commit()
        con.close()
    except Exception:  # noqa: BLE001
        pass


def log_merge(output: str, files: int, pages: int, detail: str = "") -> None:
    try:
        init_db()
        con = sqlite3.connect(db_path())
        con.execute(
            "INSERT INTO merges(ts, output, files, pages, detail)"
            " VALUES(?,?,?,?,?)",
            (time.time(), output, files, pages, detail),
        )
        con.commit()
        con.close()
    except Exception:  # noqa: BLE001
        pass


def recent_merges(limit: int = 20) -> list[tuple]:
    try:
        init_db()
        con = sqlite3.connect(db_path())
        rows = con.execute(
            "SELECT ts, output, files, pages FROM merges"
            " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return rows
    except Exception:  # noqa: BLE001
        return []
