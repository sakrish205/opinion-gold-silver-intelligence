"""
SQLite-backed TTL cache to avoid hammering yfinance on every page load.
Stores serialised DataFrames as parquet bytes or dicts as JSON.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
import time
from pathlib import Path
from typing import Any

from config import DB_PATH


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.execute("""
        CREATE TABLE IF NOT EXISTS _cache (
            key TEXT PRIMARY KEY,
            value BLOB NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    return c


def get(key: str) -> Any | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value, expires_at FROM _cache WHERE key=?", (key,)
        ).fetchone()
    if row is None:
        return None
    value_bytes, expires_at = row
    if time.time() > expires_at:
        return None  # expired; caller will refresh
    return pickle.loads(value_bytes)


def set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO _cache (key, value, expires_at) VALUES (?,?,?)",
            (key, pickle.dumps(value), time.time() + ttl_seconds),
        )


def invalidate(key: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM _cache WHERE key=?", (key,))


def purge_expired() -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM _cache WHERE expires_at < ?", (time.time(),))
