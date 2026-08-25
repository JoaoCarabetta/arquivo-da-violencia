#!/usr/bin/env python3
"""
Load official violence data from Ministry of Justice VDE dump into the database.

This script downloads and ingests VDE Formulário 1 data (victim counts by
municipality and month) from the SINESP open data portal.

Usage:
    python scripts/load_official_violence_data.py [--force] [--since YYYY-MM]

Options:
    --force          Force reload even if data already exists
    --since YYYY-MM  Only load data from this month onwards (default: 2025-09)
"""

import asyncio
import sys
import zipfile
from pathlib import Path
from io import BytesIO

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.database import get_engine, init_db
from app.services.official_violence_data import ingest_official_violence_data


VDE_DOWNLOAD_URL = "https://dados.mj.gov.br/dataset/210b9ae2-21fc-4986-89c6-2006eb4db247/resource/e9d6cc2b-33f1-468d-ab09-9aa8303c2eba/download/basededadosvde.zip"


async def download_and_parse_vde_data(since_year_month: str = "2025-09") -> list:
    """
    Download VDE zip file and parse Formulário 1 CSV.
    
    Args:
        since_year_month: Only return data >= this month (YYYY-MM format)
    
    Returns:
        List of parsed VDE data rows
    """
    logger.info(f"Downloading VDE data from {VDE_DOWNLOAD_URL}...")
    
    try:
        import httpx
        import pandas as pd
        
        # Download zip file
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(VDE_DOWNLOAD_URL)
            response.raise_for_status()
        
        logger.info(f"Downloaded {len(response.content)} bytes")
        
        # Extract CSV from zip
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            # Find Formulário 1 CSV (victim counts by municipality)
            csv_files = [name for name in zf.namelist() if name.endswith('.csv')]
            
            if not csv_files:
                raise ValueError("No CSV files found in VDE zip")
            
            # The VDE dump typically contains multiple CSVs, one per formulário
            # We need Formulário 1 (vítimas por sexo e município)
            # File naming pattern from docs: likely includes "formulario_1" or similar
            form1_file = None
            for csv_file in csv_files:
                if 'formulario' in csv_file.lower() and '1' in csv_file:
                    form1_file = csv_file
                    break
            
            if not form1_file:
                # Fallback: use first CSV (may need adjustment based on actual file structure)
                logger.warning(f"Could not identify Formulário 1 file, using first CSV: {csv_files[0]}")
                form1_file = csv_files[0]
            
            logger.info(f"Reading {form1_file} from VDE zip...")
            
            # Read CSV
            with zf.open(form1_file) as csvfile:
                df = pd.read_csv(csvfile, encoding='utf-8', dtype=str)
        
        logger.info(f"Loaded {len(df)} rows from VDE CSV")
        
        # Filter by date (>= since_year_month)
        # Convert mes_ano "MM/YYYY" to "YYYY-MM" for comparison
        def parse_mes_ano(mes_ano: str) -> str:
            month, year = mes_ano.split("/")
            return f"{year}-{month.zfill(2)}"
        
        df['year_month_parsed'] = df['mes_ano'].apply(parse_mes_ano)
        df_filtered = df[df['year_month_parsed'] >= since_year_month]
        
        logger.info(f"Filtered to {len(df_filtered)} rows >= {since_year_month}")
        
        # Convert to list of dicts
        records = df_filtered.to_dict('records')
        return records
        
    except ImportError as e:
        logger.error(f"Missing required package: {e}. Install with: pip install httpx pandas")
        raise
    except Exception as e:
        logger.error(f"Failed to download/parse VDE data: {e}")
        raise


async def main(force: bool = False, since: str = "2025-09"):
    """Load official violence data into database."""
    logger.info("=" * 80)
    logger.info(f"Loading official violence data (force={force}, since={since})")
    logger.info("=" * 80)
    
    # Initialize database tables
    await init_db()
    logger.info("Database tables verified")
    
    # Get engine
    engine = get_engine()
    
    # Download and parse VDE data
    try:
        vde_data = await download_and_parse_vde_data(since_year_month=since)
    except Exception as e:
        logger.error(f"✗ Failed to download VDE data: {e}")
        logger.info("You may need to manually download the VDE zip file and adapt this script")
        return
    
    # Ingest data
    async with AsyncSession(engine) as session:
        try:
            await ingest_official_violence_data(
                session=session,
                vde_data=vde_data
            )
            logger.success("✓ Official violence data loaded successfully")
            logger.info("=" * 80)
            logger.info("Next steps:")
            logger.info("  1. Verify: SELECT COUNT(*) FROM official_violence_count;")
            logger.info("  2. Test coverage calculation (issue 176)")
            logger.info("=" * 80)
        except Exception as e:
            logger.error(f"✗ Failed to ingest official violence data: {e}")
            raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Load official violence data from Ministry of Justice VDE"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload even if data exists"
    )
    parser.add_argument(
        "--since",
        type=str,
        default="2025-09",
        help="Only load data from this month onwards (YYYY-MM format, default: 2025-09)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(force=args.force, since=args.since))
