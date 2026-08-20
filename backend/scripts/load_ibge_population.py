#!/usr/bin/env python3
"""
Load IBGE municipality and population data from geobr + SIDRA into the database.

This script should be run once after deployment to populate the ibge_population table.

Usage:
    python scripts/load_ibge_population.py [--year 2022] [--force]

Options:
    --year YEAR    Census year (default: 2022)
    --force        Force reload even if data already exists
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.database import get_engine, init_db
from app.services.ibge_population import load_ibge_data_from_geobr_and_sidra


async def main(year: int = 2022, force: bool = False):
    """Load IBGE data into database."""
    logger.info("=" * 80)
    logger.info(f"Loading IBGE population data (year={year}, force={force})")
    logger.info("=" * 80)
    
    # Initialize database tables
    await init_db()
    logger.info("Database tables verified")
    
    # Get engine
    engine = get_engine()
    
    # Load data
    async with AsyncSession(engine) as session:
        try:
            await load_ibge_data_from_geobr_and_sidra(
                session=session,
                year=year,
                force_reload=force
            )
            logger.success("✓ IBGE data loaded successfully")
            logger.info("=" * 80)
            logger.info("Next steps:")
            logger.info("  1. Verify: SELECT COUNT(*) FROM ibge_population;")
            logger.info("  2. Test: Navigate to /estatisticas and check rates appear")
            logger.info("=" * 80)
        except Exception as e:
            logger.error(f"✗ Failed to load IBGE data: {e}")
            raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Load IBGE population data from geobr + SIDRA"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2022,
        help="Census year (default: 2022)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload even if data exists"
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(year=args.year, force=args.force))
