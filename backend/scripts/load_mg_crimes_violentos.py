#!/usr/bin/env python3
"""
Load Minas Gerais SEJUSP Crimes Violentos into OfficialViolenceCount.

Staging/dev helper for issue #243. Does not run in production cron.
Writes source_id=mg; revision defaults to consolidado (source has no fase column).

Source:
  https://dados.mg.gov.br/dataset/crimes-violentos
  Annual CSV: crimes_violentos_YYYY.csv (semicolon-separated)

Usage:
    python scripts/load_mg_crimes_violentos.py [--since YYYY-MM] [--year YYYY] [--file PATH]
    python scripts/load_mg_crimes_violentos.py --revision preliminar  # optional override
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_engine, init_db
from app.models.ibge_population import IBGEPopulation
from app.models.official_violence_data import OfficialRevision
from app.services.mg_crimes_violentos import (
    MG_CRIMES_VIOLENTOS_PORTAL,
    build_mg_ibge_lookup,
    decode_mg_bytes,
    ingest_mg_crimes_violentos_rows,
    mg_csv_url,
    parse_mg_crimes_violentos_csv,
)


async def load_mg_text(
    text: str,
    since: str,
    revision: OfficialRevision,
    ibge_lookup: dict[int, int],
) -> None:
    records = parse_mg_crimes_violentos_csv(text, since=since, ibge_lookup=ibge_lookup)
    logger.info(f"Parsed {len(records)} mapped MG rows since {since}")
    engine = get_engine()
    async with AsyncSession(engine) as session:
        await ingest_mg_crimes_violentos_rows(session, records, revision=revision)
    logger.success("MG Crimes Violentos ingest complete (source_id=mg)")


async def main(
    since: str,
    year: int,
    file_path: str | None,
    revision: OfficialRevision,
) -> None:
    await init_db()
    engine = get_engine()
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(IBGEPopulation.code_muni).where(IBGEPopulation.abbrev_state == "MG")
        )
        ibge_lookup = build_mg_ibge_lookup(code for (code,) in result.all())

    if file_path:
        raw = Path(file_path).read_bytes()
        text = decode_mg_bytes(raw)
    else:
        import httpx

        url = mg_csv_url(year)
        logger.info(f"Downloading {url} (portal: {MG_CRIMES_VIOLENTOS_PORTAL})")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "arquivo-da-violencia/1.0"},
            )
            response.raise_for_status()
        text = decode_mg_bytes(response.content)
        logger.info(f"Downloaded {len(response.content)} bytes")

    await load_mg_text(text, since=since, revision=revision, ibge_lookup=ibge_lookup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load MG SEJUSP Crimes Violentos into official store"
    )
    parser.add_argument(
        "--since",
        default="2025-09",
        help="Only ingest year-month >= this (default 2025-09)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Calendar year CSV to download when --file is omitted (default 2025)",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Local CSV extract instead of downloading from dados.mg.gov.br",
    )
    parser.add_argument(
        "--revision",
        choices=["preliminar", "consolidado"],
        default="consolidado",
        help="Revision stage (source has no fase column; default consolidado)",
    )
    args = parser.parse_args()
    revision = OfficialRevision(args.revision)
    asyncio.run(
        main(
            since=args.since,
            year=args.year,
            file_path=args.file,
            revision=revision,
        )
    )
