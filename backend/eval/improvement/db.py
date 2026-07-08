"""Read-only database access for prod anomaly detection."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import async_session_maker


class SqliteReader:
    """Read-only SQLite snapshot (matches existing eval build scripts)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> SqliteReader:
        self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def fetchall(self, query: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        assert self._conn is not None
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


async def fetch_postgres(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    async with async_session_maker() as session:
        result = await session.execute(text(query), params or {})
        return [dict(row._mapping) for row in result.fetchall()]


async def fetch_rows(db_path: Path | None, query: str, params: dict[str, Any] | None = None) -> list[dict]:
    """Fetch from SQLite snapshot or DATABASE_URL-backed Postgres."""
    if db_path is not None:
        with SqliteReader(db_path) as reader:
            if params:
                return reader.fetchall(query, tuple(params.values()))
            return reader.fetchall(query)
    return await fetch_postgres(query, params)
