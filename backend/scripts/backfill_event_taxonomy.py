#!/usr/bin/env python3
"""Backfill event_family and event_subtype from legacy homicide_type."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.database import async_session_maker
from app.taxonomy import format_legacy_homicide_type, parse_legacy_homicide_type


async def backfill_table(table: str, *, dry_run: bool) -> int:
    updated = 0
    async with async_session_maker() as session:
        result = await session.execute(
            text(f"SELECT id, homicide_type FROM {table} WHERE event_family IS NULL OR event_family = ''")
        )
        rows = result.fetchall()
        for row_id, homicide_type in rows:
            family, subtype = parse_legacy_homicide_type(homicide_type)
            label = format_legacy_homicide_type(family, subtype)
            if not dry_run:
                await session.execute(
                    text(f"""
                        UPDATE {table}
                        SET event_family = :family,
                            event_subtype = :subtype,
                            homicide_type = :label,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {
                        "id": row_id,
                        "family": family,
                        "subtype": subtype,
                        "label": label,
                    },
                )
            updated += 1
        if not dry_run:
            await session.commit()
    return updated


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for table in ("raw_event", "unique_event"):
        n = await backfill_table(table, dry_run=args.dry_run)
        mode = "would update" if args.dry_run else "updated"
        print(f"{table}: {mode} {n} rows")


if __name__ == "__main__":
    asyncio.run(main())
