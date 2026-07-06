#!/usr/bin/env python3
"""Copy data from SQLite to PostgreSQL preserving primary keys and sequences.

Usage (from repo root, with Postgres reachable):

    docker compose -f docker-compose.dev.yml run --rm api python scripts/migrate_sqlite_to_postgres.py \\
        --sqlite-url sqlite+aiosqlite:////app/instance/violence.db \\
        --postgres-url postgresql+asyncpg://arquivo:arquivo_dev@postgres:5432/arquivo_dev

On the VPS during cutover, copy the SQLite backup to a writable path and use a
sync driver URL (no aiosqlite):

    cp /root/backups/violence-pre-pg-*.db /tmp/violence-migrate.db
    docker compose -p prod run --rm --no-deps \\
      -v /tmp/violence-migrate.db:/tmp/violence-migrate.db:ro \\
      api python scripts/migrate_sqlite_to_postgres.py \\
      --sqlite-url sqlite:////tmp/violence-migrate.db \\
      --postgres-url "postgresql+asyncpg://arquivo:\${POSTGRES_PASSWORD}@postgres:5432/arquivo_prod"

Run ``alembic upgrade head`` (including the widen-text-columns migration) before
importing data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TABLES_IN_ORDER = [
    "source_google_news",
    "unique_event",
    "raw_event",
    "city_stats",
    "pipeline_attempt",
]

BATCH_SIZE = 1000


def _sync_sqlite_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://")
    return url


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _coerce_value(value, col_type):
    if value is None:
        return None
    if isinstance(col_type, DateTime) and isinstance(value, str):
        return _parse_datetime(value)
    if isinstance(col_type, Boolean):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str) and value.isdigit():
            return bool(int(value))
    if isinstance(col_type, Integer) and isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(col_type, Numeric) and isinstance(value, str):
        return Decimal(value)
    if isinstance(col_type, JSON):
        if isinstance(value, str):
            try:
                return json.dumps(json.loads(value))
            except json.JSONDecodeError:
                return value
        if isinstance(value, (dict, list)):
            return json.dumps(value)
    return value


def _coerce_row(row: dict, column_types: dict[str, object]) -> dict:
    return {
        key: _coerce_value(row.get(key), column_types.get(key))
        for key in column_types
    }


def _sqlite_count(sqlite_url: str, table: str) -> int:
    engine = create_engine(_sync_sqlite_url(sqlite_url))
    try:
        with engine.connect() as conn:
            return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
    finally:
        engine.dispose()


def _sqlite_max_id(sqlite_url: str, table: str) -> int | None:
    engine = create_engine(_sync_sqlite_url(sqlite_url))
    try:
        with engine.connect() as conn:
            value = conn.execute(text(f"SELECT MAX(id) FROM {table}")).scalar_one()
            return int(value) if value is not None else None
    finally:
        engine.dispose()


async def _pg_count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return int(result.scalar_one())


async def _pg_max_id(engine: AsyncEngine, table: str) -> int | None:
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT MAX(id) FROM {table}"))
        value = result.scalar_one()
        return int(value) if value is not None else None


async def _truncate_target(engine: AsyncEngine, tables: list[str]) -> None:
    async with engine.begin() as conn:
        for table in reversed(tables):
            await conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))


async def _copy_table(sqlite_url: str, target: AsyncEngine, table: str) -> int:
    sync_engine = create_engine(_sync_sqlite_url(sqlite_url))
    try:
        inspector = inspect(sync_engine)
        columns_meta = inspector.get_columns(table)
        columns = [col["name"] for col in columns_meta]
        column_types = {col["name"]: col["type"] for col in columns_meta}
        col_list = ", ".join(columns)
        placeholders = ", ".join(f":{col}" for col in columns)

        offset = 0
        copied = 0
        with sync_engine.connect() as src_conn:
            while True:
                result = src_conn.execute(
                    text(
                        f"SELECT {col_list} FROM {table} ORDER BY id LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": BATCH_SIZE, "offset": offset},
                )
                rows = [
                    _coerce_row(dict(row), column_types)
                    for row in result.mappings().all()
                ]
                if not rows:
                    break

                async with target.begin() as tgt_conn:
                    await tgt_conn.execute(
                        text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"),
                        rows,
                    )

                copied += len(rows)
                offset += BATCH_SIZE
                print(f"  {table}: copied {copied} rows...", flush=True)
        return copied
    finally:
        sync_engine.dispose()


async def _reset_sequences(engine: AsyncEngine, tables: list[str]) -> None:
    async with engine.begin() as conn:
        for table in tables:
            result = await conn.execute(text(f"SELECT MAX(id) FROM {table}"))
            max_id = result.scalar_one()
            if max_id is None:
                continue
            await conn.execute(
                text(
                    """
                    SELECT setval(
                        pg_get_serial_sequence(:table_name, 'id'),
                        :max_id,
                        true
                    )
                    """
                ),
                {"table_name": table, "max_id": int(max_id)},
            )


async def _verify(sqlite_url: str, target: AsyncEngine, tables: list[str]) -> bool:
    ok = True
    for table in tables:
        src_count = _sqlite_count(sqlite_url, table)
        tgt_count = await _pg_count(target, table)
        src_max = _sqlite_max_id(sqlite_url, table)
        tgt_max = await _pg_max_id(target, table)
        match = src_count == tgt_count and src_max == tgt_max
        status = "OK" if match else "MISMATCH"
        print(
            f"  [{status}] {table}: count {src_count} -> {tgt_count}, max_id {src_max} -> {tgt_max}"
        )
        ok = ok and match
    return ok


async def migrate(
    sqlite_url: str,
    postgres_url: str,
    *,
    skip_truncate: bool,
    verify_only: bool,
) -> int:
    target_engine = create_async_engine(_normalize_postgres_url(postgres_url), future=True)

    try:
        if verify_only:
            print("Verification only:")
            ok = await _verify(sqlite_url, target_engine, TABLES_IN_ORDER)
            return 0 if ok else 1

        if not skip_truncate:
            print("Truncating target tables...")
            await _truncate_target(target_engine, TABLES_IN_ORDER)

        print("Copying tables...")
        for table in TABLES_IN_ORDER:
            copied = await _copy_table(sqlite_url, target_engine, table)
            print(f"  {table}: {copied} rows total")

        print("Resetting PostgreSQL sequences...")
        await _reset_sequences(target_engine, TABLES_IN_ORDER)

        print("Verification:")
        ok = await _verify(sqlite_url, target_engine, TABLES_IN_ORDER)
        return 0 if ok else 1
    finally:
        await target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument(
        "--sqlite-url",
        default="sqlite+aiosqlite:///./instance/violence.db",
        help="Source SQLite URL (use sqlite:// for sync reads during VPS cutover)",
    )
    parser.add_argument(
        "--postgres-url",
        required=True,
        help="Target PostgreSQL URL (postgresql+asyncpg://...)",
    )
    parser.add_argument(
        "--skip-truncate",
        action="store_true",
        help="Do not truncate target tables before import",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Compare row counts without copying",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(
        asyncio.run(
            migrate(
                args.sqlite_url,
                args.postgres_url,
                skip_truncate=args.skip_truncate,
                verify_only=args.verify_only,
            )
        )
    )


if __name__ == "__main__":
    main()
