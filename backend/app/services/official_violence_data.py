"""
Official violence data service (Ministry of Justice VDE data).

This module provides functions to:
1. Ingest bancovde-YYYY.xlsx data (victim counts by municipality and month)
2. Resolve municipality names to 7-digit IBGE codes via ibge_population table
3. Calculate summed "mortes violentas intencionais" totals
4. Query official statistics with window filtering

Data source: SINESP VDE (Validador de Dados Estatísticos)
URL pattern: https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/estatistica/download/dnsp-base-de-dados/bancovde-YYYY.xlsx/@@download/file

File format: bancovde-2025.xlsx, sheet "2025", 14 columns
Headers: ["uf","municipio","evento","data_referencia","agente","arma","faixa_etaria","feminino","masculino","nao_informado","total_vitima","total","total_peso","abrangencia"]
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.models.official_violence_data import OfficialViolenceCount


# Mapping from VDE evento names to our indicator slugs
# These strings must match the exact casing in bancovde-YYYY.xlsx
INDICATOR_MAPPING = {
    "Homicídio doloso": "homicidio_doloso",
    "Feminicídio": "feminicidio",
    "Roubo seguido de morte (latrocínio)": "latrocinio",
    "Lesão corporal seguida de morte": "lesao_corporal_seguida_morte",
    "Morte por intervenção de Agente do Estado": "morte_intervencao_policial",
}

# Indicators that comprise "mortes violentas intencionais"
# Spec: homicídio doloso + feminicídio + latrocínio + lesão corporal seguida de morte + morte por intervenção do Estado
MVI_INDICATORS = [
    "homicidio_doloso",
    "feminicidio",
    "latrocinio",
    "lesao_corporal_seguida_morte",
    "morte_intervencao_policial",
]


def _excel_serial_to_year_month(serial_date: float) -> str:
    """
    Convert Excel serial date to YYYY-MM.

    Excel serial date: days since 1899-12-30 (Excel epoch)
    Examples: 45658 = 2025-01-01, 45689 = 2025-02-01

    Args:
        serial_date: Excel serial date number

    Returns:
        String in YYYY-MM format (e.g. "2025-09")
    """
    # Excel epoch is 1899-12-30
    excel_epoch = datetime(1899, 12, 30)
    date = excel_epoch + timedelta(days=int(serial_date))
    return date.strftime("%Y-%m")


async def ingest_official_violence_data(
    session: AsyncSession,
    vde_data: List[Dict[str, Any]],
    source: str = "SINESP VDE"
) -> None:
    """
    Ingest bancovde-YYYY.xlsx data (victim counts by municipality and month).

    Expected bancovde format (14 columns):
    - uf: State abbreviation (e.g. "SP")
    - municipio: Municipality name (e.g. "SÃO PAULO")
    - evento: Crime type (must match INDICATOR_MAPPING keys)
    - data_referencia: Excel serial date for first of month (e.g. 45901 = 2025-09-01)
    - agente, arma, faixa_etaria: Disaggregation dimensions (ignored for our totals)
    - feminino, masculino, nao_informado: Sex-disaggregated counts (unused - we use total_vitima)
    - total_vitima: Total victim count (sex-combined) - THIS IS WHAT WE USE
    - total, total_peso, abrangencia: Other columns (unused)

    Municipality resolution:
    - No 7-digit IBGE code in the file
    - Resolve (uf, municipio) → code_muni via ibge_population table
    - Drop rows that don't match an IBGE code

    Aggregation:
    - Rows are sliced by agente/arma/faixa_etaria
    - SUM total_vitima for same (uf, municipio, year_month, evento) before storing

    This function:
    1. Resolves municipality names to IBGE codes
    2. Groups and sums by (code_muni, year_month, indicator)
    3. Stores per-indicator counts
    4. Calculates and stores summed "mortes violentas intencionais" total
    5. Is idempotent: re-ingesting the same month updates existing rows

    Args:
        session: Database session
        vde_data: List of bancovde data rows (dicts with 14 columns)
        source: Data source description
    """
    if not vde_data:
        return

    # Import here to avoid circular dependency
    from app.services.ibge_population import lookup_city_codes

    # First pass: collect all unique (uf, municipio) pairs for batch lookup
    unique_municipalities = set()
    for row in vde_data:
        uf = row.get("uf", "").strip()
        municipio = row.get("municipio", "").strip()
        if uf and municipio:
            unique_municipalities.add((municipio, uf))

    # Batch lookup IBGE codes
    cities = [m[0] for m in unique_municipalities]
    states = [m[1] for m in unique_municipalities]
    code_lookup = await lookup_city_codes(session, cities, states)

    # Second pass: group and sum by (code_muni, year_month, indicator)
    grouped: Dict[tuple, int] = {}

    for row in vde_data:
        uf = row.get("uf", "").strip()
        municipio = row.get("municipio", "").strip()

        if not uf or not municipio:
            logger.debug(f"Missing uf/municipio in row, skipping")
            continue

        # Resolve to IBGE code
        code_muni = code_lookup.get((municipio, uf))
        if not code_muni:
            logger.debug(f"Could not resolve IBGE code for {municipio}/{uf}, skipping")
            continue

        # Parse evento
        evento = row.get("evento", "").strip()
        if evento not in INDICATOR_MAPPING:
            # Ignore other eventos
            continue

        indicator = INDICATOR_MAPPING[evento]

        # Parse date
        data_ref = row.get("data_referencia")
        if not data_ref:
            logger.debug(f"Missing data_referencia in row, skipping")
            continue

        try:
            year_month = _excel_serial_to_year_month(float(data_ref))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid data_referencia {data_ref}: {e}")
            continue

        # Parse victim count
        total_vitima = row.get("total_vitima")
        if total_vitima is None or total_vitima == "":
            victim_count = 0
        else:
            try:
                victim_count = int(float(total_vitima))
            except (ValueError, TypeError):
                logger.warning(f"Invalid total_vitima value: {total_vitima}")
                continue

        # Group key
        key = (code_muni, year_month, indicator)
        grouped[key] = grouped.get(key, 0) + victim_count

    # Convert to nested dict for storage
    storage_grouped: Dict[tuple, Dict[str, int]] = {}
    for (code_muni, year_month, indicator), victim_count in grouped.items():
        key = (code_muni, year_month)
        if key not in storage_grouped:
            storage_grouped[key] = {}
        storage_grouped[key][indicator] = victim_count

    # Insert/update rows (explicit upsert for idempotence)
    for (code_muni, year_month), indicators in storage_grouped.items():
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
    logger.info(f"Ingested official violence data for {len(storage_grouped)} municipality-months")


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
