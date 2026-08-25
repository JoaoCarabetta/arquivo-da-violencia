#!/usr/bin/env python3
"""
Load official violence data from Ministry of Justice VDE dump into the database.

This script downloads and ingests VDE municipal data (victim counts by
municipality and month) from the SINESP open data portal.

Data sources on https://dados.mj.gov.br/dataset/sistema-nacional-de-estatisticas-de-seguranca-publica :
- XLSX: "Dados Nacionais de Segurança Pública - Municípios" (recommended)
- ZIP: "Base de Dados VDE" (raw VDE dump, multiple formulários)

Usage:
    python scripts/load_official_violence_data.py [--since YYYY-MM] [--source XLSX|ZIP]

Options:
    --since YYYY-MM  Only load data from this month onwards (default: 2025-09)
    --source TYPE    Data source: XLSX (municipal aggregated) or ZIP (raw VDE)
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

# Official data URLs from dados.mj.gov.br
VDE_ZIP_URL = "https://dados.mj.gov.br/dataset/210b9ae2-21fc-4986-89c6-2006eb4db247/resource/e9d6cc2b-33f1-468d-ab09-9aa8303c2eba/download/basededadosvde.zip"
VDE_XLSX_URL = "https://dados.mj.gov.br/dataset/210b9ae2-21fc-4986-89c6-2006eb4db247/resource/03af7ce2-174e-4ebd-b085-384503cfb40f/download/dados-nacionais-seguranca-publica-municipios.xlsx"

async def download_and_parse_vde_xlsx(since_year_month: str = "2025-09") -> list:
    """
    Download and parse municipal XLSX file (recommended).

    This file contains aggregated municipal-level indicators.
    Expected columns (based on common Brazilian government data patterns):
    - ano, mes, uf, municipio, cod_municipio (or similar)
    - One column per indicator, or tipo_crime/indicador column (long format)

    Args:
        since_year_month: Only return data >= this month (YYYY-MM format)

    Returns:
        List of parsed VDE data rows (dicts)
    """
    logger.info(f"Downloading VDE municipal XLSX from {VDE_XLSX_URL}...")

    try:
        import httpx
        import pandas as pd

        # Download XLSX
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(VDE_XLSX_URL)
            response.raise_for_status()

        logger.info(f"Downloaded {len(response.content)} bytes")

        # Parse XLSX
        df = pd.read_excel(BytesIO(response.content), dtype=str)
        logger.info(f"Loaded {len(df)} rows from XLSX")
        logger.info(f"Columns: {list(df.columns)}")

        # Normalize column names (lowercase, strip spaces)
        df.columns = df.columns.str.strip().str.lower()

        # Filter by date
        # Try to construct year-month from ano + mes columns
        if 'ano' in df.columns and 'mes' in df.columns:
            df['year_month_parsed'] = df.apply(
                lambda row: f"{row['ano']}-{str(int(row['mes'])).zfill(2)}"
                if row['mes'].isdigit() else None,
                axis=1
            )
            df_filtered = df[df['year_month_parsed'] >= since_year_month]
        else:
            logger.warning("Could not find ano/mes columns, returning all rows")
            df_filtered = df

        logger.info(f"Filtered to {len(df_filtered)} rows >= {since_year_month}")

        # Convert to list of dicts
        records = df_filtered.to_dict('records')
        return records

    except ImportError as e:
        logger.error(f"Missing required package: {e}. Install with: pip install httpx pandas openpyxl")
        raise
    except Exception as e:
        logger.error(f"Failed to download/parse VDE XLSX: {e}")
        raise

async def download_and_parse_vde_zip(since_year_month: str = "2025-09") -> list:
    """
    Download and parse VDE ZIP file (raw VDE dump, multiple formulários).

    This is the comprehensive VDE export. We need to identify and parse
    Formulário 1 and Formulário 3 for the 5 MVI indicators.

    Args:
        since_year_month: Only return data >= this month (YYYY-MM format)

    Returns:
        List of parsed VDE data rows (dicts)
    """
    logger.info(f"Downloading VDE zip from {VDE_ZIP_URL}...")

    try:
        import httpx
        import pandas as pd

        # Download zip
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(VDE_ZIP_URL)
            response.raise_for_status()

        logger.info(f"Downloaded {len(response.content)} bytes")

        # Extract and identify relevant files
        with zipfile.ZipFile(BytesIO(response.content)) as zf:
            logger.info(f"Files in VDE zip: {zf.namelist()}")

            # Find Formulário 1 and Formulário 3 CSV files
            # Expected patterns: "formulario_1", "form1", "formulario1", etc.
            form1_file = None
            form3_file = None

            for filename in zf.namelist():
                if not filename.endswith('.csv'):
                    continue
                lower_name = filename.lower()
                if 'formulario' in lower_name or 'form' in lower_name:
                    if '1' in lower_name and not form1_file:
                        form1_file = filename
                    elif '3' in lower_name and not form3_file:
                        form3_file = filename

            if not form1_file:
                raise ValueError(
                    f"Could not identify Formulário 1 file in VDE zip. "
                    f"Files found: {zf.namelist()}"
                )

            logger.info(f"Reading Formulário 1: {form1_file}")
            with zf.open(form1_file) as csvfile:
                df1 = pd.read_csv(csvfile, encoding='utf-8', dtype=str)

            all_rows = []
            all_rows.extend(df1.to_dict('records'))

            # Also read Formulário 3 if found (for "Morte por Intervenção de Agente do Estado")
            if form3_file:
                logger.info(f"Reading Formulário 3: {form3_file}")
                with zf.open(form3_file) as csvfile:
                    df3 = pd.read_csv(csvfile, encoding='utf-8', dtype=str)
                all_rows.extend(df3.to_dict('records'))
            else:
                logger.warning("Formulário 3 not found; 'Morte por Intervenção de Agente do Estado' will be missing")

            logger.info(f"Loaded {len(all_rows)} total rows from VDE")

            # Filter by date
            # TODO: Implement date filtering based on actual column structure
            # This depends on the real VDE file format

            return all_rows

    except ImportError as e:
        logger.error(f"Missing required package: {e}. Install with: pip install httpx pandas")
        raise
    except Exception as e:
        logger.error(f"Failed to download/parse VDE ZIP: {e}")
        raise

async def main(since: str = "2025-09", source: str = "XLSX"):
    """Load official violence data into database."""
    logger.info("=" * 80)
    logger.info(f"Loading official violence data (source={source}, since={since})")
    logger.info("=" * 80)

    # Initialize database tables
    await init_db()
    logger.info("Database tables verified")

    # Get engine
    engine = get_engine()

    # Download and parse VDE data
    try:
        if source.upper() == "XLSX":
            vde_data = await download_and_parse_vde_xlsx(since_year_month=since)
        else:
            vde_data = await download_and_parse_vde_zip(since_year_month=since)
    except Exception as e:
        logger.error(f"✗ Failed to download VDE data: {e}")
        logger.info("Manual alternative: Download the file from dados.mj.gov.br and adapt this script")
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
        "--since",
        type=str,
        default="2025-09",
        help="Only load data from this month onwards (YYYY-MM format, default: 2025-09)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="XLSX",
        choices=["XLSX", "ZIP"],
        help="Data source: XLSX (municipal aggregated, recommended) or ZIP (raw VDE)"
    )

    args = parser.parse_args()

    asyncio.run(main(since=args.since, source=args.source))
