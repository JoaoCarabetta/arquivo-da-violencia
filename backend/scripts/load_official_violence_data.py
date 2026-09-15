#!/usr/bin/env python3
"""
Load official violence data from Ministry of Justice bancovde-YYYY.xlsx into the database.

This script downloads and ingests municipal victim counts by month from the
SINESP VDE (Validador de Dados Estatísticos) open data portal on gov.br.

Data source: https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica/download/dnsp-base-de-dados/
URL pattern: bancovde-YYYY.xlsx

Revision: the workbook has no revision column. Pass --revision preliminar|consolidado
to tag the snapshot stage at ingest time (see official_violence_data module docstring).

Usage:
    python scripts/load_official_violence_data.py [--year YYYY] [--since YYYY-MM] [--revision preliminar|consolidado]
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.database import get_engine, init_db
from app.models.official_violence_data import OfficialRevision, OfficialSourceId
from app.services.official_violence_data import (
    BANCOVDE_WINDOW_START,
    download_bancovde_workbook,
    ingest_official_violence_data,
    parse_bancovde_workbook,
)


async def main(
    year: int = 2025,
    since: str = BANCOVDE_WINDOW_START,
    revision: OfficialRevision = OfficialRevision.CONSOLIDADO,
):
    """Load official violence data into database."""
    logger.info("=" * 80)
    logger.info(
        "Loading official violence data (bancovde-%s.xlsx, since=%s, revision=%s)",
        year,
        since,
        revision.value,
    )
    logger.info("=" * 80)

    await init_db()
    logger.info("Database tables verified")

    engine = get_engine()

    try:
        workbook_bytes = await download_bancovde_workbook(year=year)
        vde_data = parse_bancovde_workbook(
            workbook_bytes,
            year=year,
            since_year_month=since,
        )
    except Exception as e:
        logger.error("✗ Failed to download/parse bancovde data: %s", e)
        logger.info(
            "Manual alternative: download bancovde-%s.xlsx from gov.br and pass "
            "rows to ingest_official_violence_data() with revision=%s",
            year,
            revision.value,
        )
        return

    async with AsyncSession(engine) as session:
        try:
            await ingest_official_violence_data(
                session=session,
                vde_data=vde_data,
                source_id=OfficialSourceId.VALIDADOR,
                revision=revision,
            )
            logger.success("✓ Official violence data loaded successfully")
            logger.info("=" * 80)
            logger.info("Next steps:")
            logger.info("  1. Verify: SELECT COUNT(*) FROM official_violence_count;")
            logger.info("  2. Test coverage calculation (staging)")
            logger.info("=" * 80)
        except Exception as e:
            logger.error("✗ Failed to ingest official violence data: %s", e)
            raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Load official violence data from Ministry of Justice bancovde-YYYY.xlsx"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2025,
        help="Year to download (default: 2025)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=BANCOVDE_WINDOW_START,
        help="Only load data from this month onwards (YYYY-MM format, default: 2025-09)",
    )
    parser.add_argument(
        "--revision",
        type=str,
        choices=[r.value for r in OfficialRevision],
        default=OfficialRevision.CONSOLIDADO.value,
        help=(
            "Revision stage for this snapshot (default: consolidado). "
            "The bancovde workbook does not encode revision; assign it at ingest."
        ),
    )

    args = parser.parse_args()

    asyncio.run(
        main(
            year=args.year,
            since=args.since,
            revision=OfficialRevision(args.revision),
        )
    )
