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
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.models.official_violence_data import OfficialViolenceCount


# Mapping from VDE crime type names to our indicator slugs
INDICATOR_MAPPING = {
    "Homicídio Doloso": "homicidio_doloso",
    "Feminicídio": "feminicidio",
    "Roubo Seguido de Morte (Latrocínio)": "latrocinio",
    "Lesão Corporal Seguida de Morte": "lesao_corporal_seguida_morte",
    "Morte Decorrente de Intervenção Policial": "morte_intervencao_policial",
}

# Indicators that comprise "mortes violentas intencionais"
MVI_INDICATORS = [
    "homicidio_doloso",
    "feminicidio",
    "latrocinio",
    "lesao_corporal_seguida_morte",
    "morte_intervencao_policial",
]


def _parse_year_month(mes_ano: str) -> str:
    """
    Convert VDE date format to YYYY-MM.
    
    VDE format: "MM/YYYY" (e.g. "09/2025")
    Our format: "YYYY-MM" (e.g. "2025-09")
    """
    month, year = mes_ano.split("/")
    return f"{year}-{month.zfill(2)}"


async def ingest_official_violence_data(
    session: AsyncSession,
    vde_data: List[Dict[str, Any]],
    source: str = "SINESP VDE - Formulário 1"
) -> None:
    """
    Ingest VDE Formulário 1 data (victim counts by municipality and month).
    
    This function:
    1. Parses VDE data rows
    2. Stores per-indicator counts
    3. Calculates and stores summed "mortes violentas intencionais" total
    4. Is idempotent: re-ingesting the same month overwrites
    
    Args:
        session: Database session
        vde_data: List of VDE Formulário 1 rows (dicts)
        source: Data source description
    
    Example VDE row:
        {
            "mes_ano": "09/2025",
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Homicídio Doloso",
            "vitimas_masculinas": 45,
            "vitimas_femininas": 8,
            "vitimas_nao_identificadas": 0,
        }
    """
    if not vde_data:
        return
    
    # Group by (code_muni, year_month) for idempotent upsert
    grouped: Dict[tuple, Dict[str, int]] = {}
    
    for row in vde_data:
        code_muni = int(row["cod_municipio"])
        year_month = _parse_year_month(row["mes_ano"])
        tipo_crime = row["tipo_crime"]
        
        # Skip unknown crime types
        if tipo_crime not in INDICATOR_MAPPING:
            logger.warning(f"Unknown crime type in VDE data: {tipo_crime}")
            continue
        
        indicator = INDICATOR_MAPPING[tipo_crime]
        
        # Sum all victims (male + female + unidentified)
        victim_count = (
            int(row.get("vitimas_masculinas", 0)) +
            int(row.get("vitimas_femininas", 0)) +
            int(row.get("vitimas_nao_identificadas", 0))
        )
        
        key = (code_muni, year_month)
        if key not in grouped:
            grouped[key] = {}
        
        grouped[key][indicator] = victim_count
    
    # Delete existing rows for these (code_muni, year_month) pairs to ensure idempotence
    for (code_muni, year_month) in grouped.keys():
        delete_stmt = delete(OfficialViolenceCount).where(
            OfficialViolenceCount.code_muni == code_muni,
            OfficialViolenceCount.year_month == year_month
        )
        await session.execute(delete_stmt)
    
    # Insert new rows
    for (code_muni, year_month), indicators in grouped.items():
        # Store individual indicators
        for indicator, victim_count in indicators.items():
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
