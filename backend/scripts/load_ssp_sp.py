#!/usr/bin/env python3
"""
Load São Paulo SSP resolução 160 municipal-monthly counts into OfficialViolenceCount.

Staging/dev helper for issue #244. Does not run in production cron.
Writes source_id=sp with revision from the extract `revisao` column.

Source (official monthly table, NOT Transparência SSP BO dump):
  https://www.ssp.sp.gov.br/estatistica/dados-mensais
  Resolução SSP 160/2001. Portal is HTML (natureza × months per município);
  there is no stable statewide bulk CSV. Pass an unpivoted long extract via
  --file (codigo_ibge;municipio;ano;mes;natureza;vitimas;revisao).

Usage:
    python scripts/load_ssp_sp.py --file PATH [--since YYYY-MM]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_engine, init_db
from app.services.ssp_sp import (
    SSP_SP_PORTAL_URL,
    decode_ssp_sp_bytes,
    ingest_ssp_sp_rows,
    parse_ssp_sp_csv,
)


async def load_ssp_sp_text(text: str, since: str) -> None:
    await init_db()
    records = parse_ssp_sp_csv(text, since=since)
    logger.info(f"Parsed {len(records)} mapped SSP-SP rows since {since}")
    engine = get_engine()
    async with AsyncSession(engine) as session:
        await ingest_ssp_sp_rows(session, records)
    logger.success("SSP-SP resolução 160 ingest complete (source_id=sp)")


async def main(since: str, file_path: str) -> None:
    raw = Path(file_path).read_bytes()
    text = decode_ssp_sp_bytes(raw)
    logger.info(
        f"Loading extract {file_path} ({len(raw)} bytes); portal: {SSP_SP_PORTAL_URL}"
    )
    await load_ssp_sp_text(text, since=since)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load SP SSP resolução 160 monthly counts into official store"
    )
    parser.add_argument(
        "--since",
        default="2025-09",
        help="Only ingest year-month >= this (default 2025-09)",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Local long CSV extract (unpivoted dados-mensais table)",
    )
    args = parser.parse_args()
    asyncio.run(main(since=args.since, file_path=args.file))
