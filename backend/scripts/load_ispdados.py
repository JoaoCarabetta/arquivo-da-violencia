#!/usr/bin/env python3
"""
Load Rio de Janeiro ISPDados municipal-monthly counts into OfficialViolenceCount.

Staging/dev helper for issue #242. Does not run in production cron.
Writes source_id=rj with revision from the ISP `fase` column.

Source:
  https://www.ispdados.rj.gov.br/Arquivos/BaseMunicipioMensal.csv
  Portal: https://www.ispdados.rj.gov.br/estatistica.html

Usage:
    python scripts/load_ispdados.py [--since YYYY-MM] [--file PATH]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_engine, init_db
from app.services.ispdados import (
    ISPDADOS_CSV_URL,
    decode_ispdados_bytes,
    ingest_ispdados_rows,
    parse_ispdados_csv,
)


async def load_ispdados_text(text: str, since: str) -> None:
    await init_db()
    records = parse_ispdados_csv(text, since=since)
    logger.info(f"Parsed {len(records)} mapped ISPDados rows since {since}")
    engine = get_engine()
    async with AsyncSession(engine) as session:
        await ingest_ispdados_rows(session, records)
    logger.success("ISPDados ingest complete (source_id=rj)")


async def main(since: str, file_path: str | None) -> None:
    if file_path:
        raw = Path(file_path).read_bytes()
        text = decode_ispdados_bytes(raw)
    else:
        import httpx

        logger.info(f"Downloading {ISPDADOS_CSV_URL}")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(ISPDADOS_CSV_URL)
            response.raise_for_status()
        text = decode_ispdados_bytes(response.content)
        logger.info(f"Downloaded {len(response.content)} bytes")

    await load_ispdados_text(text, since=since)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load RJ ISPDados into official store")
    parser.add_argument(
        "--since",
        default="2025-09",
        help="Only ingest year-month >= this (default 2025-09)",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Local CSV extract instead of downloading the live ISPDados file",
    )
    args = parser.parse_args()
    asyncio.run(main(since=args.since, file_path=args.file))
