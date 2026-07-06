#!/usr/bin/env python3
"""Copy data from SQLite to PostgreSQL preserving primary keys and sequences.

Usage (from repo root, with Postgres reachable):

    docker compose -f docker-compose.dev.yml run --rm api python scripts/migrate_sqlite_to_postgres.py \\
        --sqlite-url sqlite+aiosqlite:////app/instance/violence.db \\
        --postgres-url postgresql+asyncpg://arquivo:arquivo_dev@postgres:5432/arquivo_dev

On the VPS during cutover, point --sqlite-url at the production backup and
--postgres-url at arquivo_prod or arquivo_staging.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

TABLES_IN_ORDER = [
    "source_google_news",
    "unique_event",
    "raw_event",
    "city_stats",
    "pipeline_attempt",
]

BATCH_SIZE = 1000


def _normalize_sqlite_url(url: str) -> str:
    if url.startswith("sqlite:///") and "+aiosqlite" not in url:
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def _count_rows(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return int(result.scalar_one())


async def _max_id(engine: AsyncEngine, table: str) -> int | None:
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT MAX(id) FROM {table}"))
        value = result.scalar_one()
        return int(value) if value is not None else None


async def _truncate_target(engine: AsyncEngine, tables: list[str]) -> None:
    async with engine.begin() as conn:
        for table in reversed(tables):
            await conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))


async def _copy_table(
    source: AsyncEngine,
    target: AsyncEngine,
    table: str,
) -> int:
    async with source.connect() as src_conn:
        inspector = inspect(source.sync_engine)
        columns = [col["name"] for col in inspector.get_columns(table)]
        col_list = ", ".join(columns)
        placeholders = ", ".join(f":{col}" for col in columns)

        offset = 0
        copied = 0
        while True:
            result = await src_conn.execute(
                text(f"SELECT {col_list} FROM {table} ORDER BY id LIMIT :limit OFFSET :offset"),
                {"limit": BATCH_SIZE, "offset": offset},
            )
            rows = result.mappings().all()
            if not rows:
                break

            async with target.begin() as tgt_conn:
                await tgt_conn.execute(
                    text(
                        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
                    ),
                    [dict(row) for row in rows],
                )

            copied += len(rows)
            offset += BATCH_SIZE
            print(f"  {table}: copied {copied} rows...", flush=True)

    return copied


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


async def _verify(source: AsyncEngine, target: AsyncEngine, tables: list[str]) -> bool:
    ok = True
    for table in tables:
        src_count = await _count_rows(source, table)
        tgt_count = await _count_rows(target, table)
        src_max = await _max_id(source, table)
        tgt_max = await _max_id(target, table)
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
    source_engine = create_async_engine(_normalize_sqlite_url(sqlite_url), future=True)
    target_engine = create_async_engine(_normalize_postgres_url(postgres_url), future=True)

    try:
        if verify_only:
            print("Verification only:")
            ok = await _verify(source_engine, target_engine, TABLES_IN_ORDER)
            return 0 if ok else 1

        if not skip_truncate:
            print("Truncating target tables...")
            await _truncate_target(target_engine, TABLES_IN_ORDER)

        print("Copying tables...")
        for table in TABLES_IN_ORDER:
            copied = await _copy_table(source_engine, target_engine, table)
            print(f"  {table}: {copied} rows total")

        print("Resetting PostgreSQL sequences...")
        await _reset_sequences(target_engine, TABLES_IN_ORDER)

        print("Verification:")
        ok = await _verify(source_engine, target_engine, TABLES_IN_ORDER)
        return 0 if ok else 1
    finally:
        await source_engine.dispose()
        await target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument(
        "--sqlite-url",
        default="sqlite+aiosqlite:///./instance/violence.db",
        help="Source SQLite URL",
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

    exit_code = asyncio.run(
        migrate(
            args.sqlite_url,
            args.postgres_url,
            skip_truncate=args.skip_truncate,
            verify_only=args.verify_only,
        )
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
