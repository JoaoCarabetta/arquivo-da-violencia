"""
Official violence data service (Ministry of Justice VDE data).

This module provides functions to:
1. Ingest VDE Formulário 1 data (victim counts by municipality and month)
2. Calculate summed "mortes violentas intencionais" totals
3. Query official statistics with window filtering

Data source: SINESP VDE (Validador de Dados Estatísticos)
URL: https://dados.mj.gov.br/dataset/sistema-nacional-de-estatisticas-de-seguranca-publica
"""

from typing import Dict, List, Any
from datetime import datetime
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.models.official_violence_data import OfficialViolenceCount

# Mapping from VDE crime type names to our indicator slugs
# These strings must match the exact names in the Ministry of Justice VDE dump
INDICATOR_MAPPING = {
    "Homicídio Doloso": "homicidio_doloso",
    "Feminicídio": "feminicidio",
    "Roubo Seguido de Morte (Latrocínio)": "latrocinio",
    "Lesão Corporal Seguida de Morte": "lesao_corporal_seguida_morte",
    "Morte por Intervenção de Agente do Estado": "morte_intervencao_policial",
}

# Indicators that comprise "mortes violentas intencionais"
MVI_INDICATORS = [
    "homicidio_doloso",
    "feminicidio",
    "latrocinio",
    "lesao_corporal_seguida_morte",
    "morte_intervencao_policial",
]

def _parse_year_month(mes: str, ano: str) -> str:
    """
    Convert VDE date fields to YYYY-MM.

    VDE format: separate mes (month as string or number) and ano (year) columns
    Our format: "YYYY-MM" (e.g. "2025-09")

    Args:
        mes: Month (can be "Janeiro", "janeiro", "1", "01", etc.)
        ano: Year (e.g. "2025")

    Returns:
        String in YYYY-MM format
    """
    # Handle month names (Portuguese)
    month_map = {
        "janeiro": "01", "fevereiro": "02", "março": "03", "abril": "04",
        "maio": "05", "junho": "06", "julho": "07", "agosto": "08",
        "setembro": "09", "outubro": "10", "novembro": "11", "dezembro": "12"
    }

    mes_lower = str(mes).lower().strip()
    if mes_lower in month_map:
        month = month_map[mes_lower]
    else:
        # Try as numeric
        month = str(int(mes)).zfill(2)

    return f"{ano}-{month}"

async def ingest_official_violence_data(
    session: AsyncSession,
    vde_data: List[Dict[str, Any]],
    source: str = "SINESP VDE"
) -> None:
    """
    Ingest VDE data (victim counts by municipality and month).

    Expected VDE data format (based on Ministry of Justice open data structure):
    - ano: Year (e.g. "2025")
    - mes: Month (e.g. "9", "09", or "Setembro")
    - uf: State abbreviation (e.g. "SP")
    - municipio: Municipality name (e.g. "São Paulo")
    - cod_municipio or municipio_codigo: 7-digit IBGE code (e.g. "3550308")
    - tipo_crime or indicador: Crime type indicator name
    - vitimas or total_vitimas: Total victim count (or separate by sex)

    This function:
    1. Parses VDE data rows
    2. Stores per-indicator counts
    3. Calculates and stores summed "mortes violentas intencionais" total
    4. Is idempotent: re-ingesting the same month overwrites (via unique constraint)

    Args:
        session: Database session
        vde_data: List of VDE data rows (dicts)
        source: Data source description
    """
    if not vde_data:
        return

    # Group by (code_muni, year_month) for batch processing
    grouped: Dict[tuple, Dict[str, int]] = {}

    for row in vde_data:
        # Parse municipality code (try multiple common column names)
        code_muni_str = row.get("cod_municipio") or row.get("municipio_codigo") or row.get("codigo_municipio")
        if not code_muni_str:
            logger.warning(f"Missing municipality code in VDE row, skipping: {row}")
            continue
        code_muni = int(code_muni_str)

        # Parse year-month
        ano = str(row.get("ano", ""))
        mes = str(row.get("mes", ""))
        if not ano or not mes:
            logger.warning(f"Missing ano/mes in VDE row, skipping: {row}")
            continue
        year_month = _parse_year_month(mes, ano)

        # Parse crime type (try multiple common column names)
        tipo_crime = row.get("tipo_crime") or row.get("indicador") or row.get("evento")
        if not tipo_crime:
            logger.warning(f"Missing crime type in VDE row, skipping: {row}")
            continue

        # Skip unknown crime types
        if tipo_crime not in INDICATOR_MAPPING:
            logger.debug(f"Unknown crime type in VDE data (not in MVI bag): {tipo_crime}")
            continue

        indicator = INDICATOR_MAPPING[tipo_crime]

        # Parse victim count (try multiple common patterns)
        if "vitimas" in row:
            victim_count = int(row["vitimas"])
        elif "total_vitimas" in row:
            victim_count = int(row["total_vitimas"])
        elif all(k in row for k in ["vitimas_masculinas", "vitimas_femininas"]):
            # Sum by sex if separate columns
            victim_count = (
                int(row.get("vitimas_masculinas", 0)) +
                int(row.get("vitimas_femininas", 0)) +
                int(row.get("vitimas_nao_identificadas", 0))
            )
        elif "ocorrencias" in row:
            # Some VDE files use "ocorrencias" instead of "vitimas"
            victim_count = int(row["ocorrencias"])
        else:
            logger.warning(f"Missing victim count in VDE row, skipping: {row}")
            continue

        key = (code_muni, year_month)
        if key not in grouped:
            grouped[key] = {}

        grouped[key][indicator] = victim_count

    # Insert/update rows (unique constraint handles idempotence)
    for (code_muni, year_month), indicators in grouped.items():
        # Store individual indicators
        for indicator, victim_count in indicators.items():
            # Check if row exists
            query_existing = select(OfficialViolenceCount).where(
                OfficialViolenceCount.code_muni == code_muni,
                OfficialViolenceCount.year_month == year_month,
                OfficialViolenceCount.indicator == indicator
            )
            result = await session.execute(query_existing)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing row
                existing.victim_count = victim_count
                existing.updated_at = datetime.utcnow()
            else:
                # Insert new row
                count_row = OfficialViolenceCount(
                    code_muni=code_muni,
                    year_month=year_month,
                    indicator=indicator,
                    victim_count=victim_count,
                    is_total=False,
                    source=source
                )
                session.add(count_row)

        # Calculate and store summed "mortes violentas intencionais" total
        mvi_total = sum(indicators.get(ind, 0) for ind in MVI_INDICATORS)

        query_existing_total = select(OfficialViolenceCount).where(
            OfficialViolenceCount.code_muni == code_muni,
            OfficialViolenceCount.year_month == year_month,
            OfficialViolenceCount.indicator == "mortes_violentas_intencionais"
        )
        result = await session.execute(query_existing_total)
        existing_total = result.scalar_one_or_none()

        if existing_total:
            # Update existing total
            existing_total.victim_count = mvi_total
            existing_total.updated_at = datetime.utcnow()
        else:
            # Insert new total
            total_row = OfficialViolenceCount(
                code_muni=code_muni,
                year_month=year_month,
                indicator="mortes_violentas_intencionais",
                victim_count=mvi_total,
                is_total=True,
                source=source
            )
            session.add(total_row)

    await session.commit()
    logger.info(f"Ingested official violence data for {len(grouped)} municipality-months")

async def get_official_violence_totals(
    session: AsyncSession,
    code_munis: List[int],
    min_year_month: str = "2025-09"
) -> List[Dict[str, Any]]:
    """
    Get official "mortes violentas intencionais" totals for municipalities.

    Args:
        session: Database session
        code_munis: List of IBGE municipal codes
        min_year_month: Minimum year-month (YYYY-MM) to include (default: 2025-09)

    Returns:
        List of dicts with keys: code_muni, year_month, victim_count
    """
    if not code_munis:
        return []

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni.in_(code_munis),
        OfficialViolenceCount.indicator == "mortes_violentas_intencionais",
        OfficialViolenceCount.year_month >= min_year_month
    ).order_by(
        OfficialViolenceCount.code_muni,
        OfficialViolenceCount.year_month
    )

    result = await session.execute(query)
    counts = result.scalars().all()

    return [
        {
            "code_muni": c.code_muni,
            "year_month": c.year_month,
            "victim_count": c.victim_count
        }
        for c in counts
    ]
