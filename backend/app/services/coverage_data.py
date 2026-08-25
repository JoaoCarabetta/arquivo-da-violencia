"""
Coverage data aggregator: Arquivo vs Official violence statistics.

Combines:
1. Official municipal total counts from Ministry of Justice VDE data (Formulário 1 only)
2. Arquivo victim counts from UniqueEvent (public incident filter)
3. Municipality metadata from IBGE population table

Returns coverage table for /estatisticas page.
Window: 2025-09-01 through latest official month.

Official total = 4 Formulário 1 types only:
- homicídio doloso
- feminicídio
- roubo seguido de morte (latrocínio)
- lesão corporal seguida de morte
DO NOT include morte por intervenção de agente do Estado in the municipal total.
"""

from typing import Dict, List, Any
from datetime import datetime
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.models.official_violence_data import OfficialViolenceCount
from app.models.unique_event import UniqueEvent
from app.models.ibge_population import IBGEPopulation
from app.services.public_filters import public_incident_criteria


# Coverage window: complete months from 2025-09 onwards
# (first full month after Arquivo start 2025-08-26)
COVERAGE_WINDOW_START = datetime(2025, 9, 1)


async def get_coverage_data(
    session: AsyncSession,
    min_year_month: str = "2025-09"
) -> List[Dict[str, Any]]:
    """
    Get coverage data: union of municipalities with official > 0 OR Arquivo > 0.
    
    Aggregates:
    - Official municipal total counts by municipality (Formulário 1 types only)
    - Arquivo victim counts (public incident filter, Brazil only, >= 2025-09)
    - Coverage = Arquivo / official (not capped, None when official=0)
    
    Args:
        session: Database session
        min_year_month: Minimum year-month (YYYY-MM) for window start
    
    Returns:
        List of dicts with keys:
        - code: 7-digit IBGE municipal code
        - name: Municipality name
        - uf: State abbreviation (e.g. "SP", "RJ")
        - official_victims: Official municipal total count (Formulário 1 types only)
        - arquivo_victims: Arquivo victim count (public filter)
        - coverage: Arquivo / official ratio (None when official=0)
        
        Sorted by official_victims descending.
    
    Acceptance criteria:
    - Official 0 + Arquivo > 0 → row exists, coverage=None
    - Official 0 + Arquivo 0 → row absent (hidden)
    - Official 10 + Arquivo 12 → coverage=1.2 (not capped)
    - Event without municipality_code → absent
    - Non-Brazil event → absent
    - Event before 2025-09-01 → absent from Arquivo count
    """
    
    # 1. Get official counts (Formulário 1 types only) by municipality
    official_query = select(
        OfficialViolenceCount.code_muni,
        func.sum(OfficialViolenceCount.victim_count).label("official_victims")
    ).where(
        OfficialViolenceCount.indicator == "mortes_violentas_intencionais",
        OfficialViolenceCount.year_month >= min_year_month
    ).group_by(OfficialViolenceCount.code_muni)
    
    official_result = await session.execute(official_query)
    official_rows = official_result.all()
    
    official_by_code: Dict[int, int] = {
        row.code_muni: row.official_victims for row in official_rows
    }
    
    logger.info(f"Loaded official counts for {len(official_by_code)} municipalities")
    
    # 2. Get Arquivo victim counts by municipality_code
    # Public incident filter: homicidio, incident, victim_count <= 10
    # Country=BR (or Brasil), event_date >= 2025-09-01
    # Grouped by municipality_code (events without code are excluded)
    
    arquivo_query = select(
        UniqueEvent.municipality_code,
        func.sum(UniqueEvent.victim_count).label("arquivo_victims")
    ).where(
        UniqueEvent.municipality_code.isnot(None),  # Must have code
        UniqueEvent.event_date >= COVERAGE_WINDOW_START,
        # Country filter: BR or legacy "Brasil"
        (UniqueEvent.country == "BR") | (UniqueEvent.country == "Brasil")
    )
    
    # Apply public incident criteria (homicidio, incident, victim_count <= 10)
    for criterion in public_incident_criteria(country="BR"):
        arquivo_query = arquivo_query.where(criterion)
    
    arquivo_query = arquivo_query.group_by(UniqueEvent.municipality_code)
    
    arquivo_result = await session.execute(arquivo_query)
    arquivo_rows = arquivo_result.all()
    
    arquivo_by_code: Dict[int, int] = {
        row.municipality_code: row.arquivo_victims for row in arquivo_rows if row.municipality_code
    }
    
    logger.info(f"Loaded Arquivo counts for {len(arquivo_by_code)} municipalities")
    
    # 3. Union: all municipalities with official > 0 OR Arquivo > 0
    all_codes = set(official_by_code.keys()) | set(arquivo_by_code.keys())
    
    if not all_codes:
        logger.warning("No municipalities found with official or Arquivo data")
        return []
    
    # 4. Fetch IBGE metadata for all municipalities
    ibge_query = select(IBGEPopulation).where(
        IBGEPopulation.code_muni.in_(list(all_codes))
    )
    ibge_result = await session.execute(ibge_query)
    ibge_records = ibge_result.scalars().all()
    
    ibge_by_code: Dict[int, IBGEPopulation] = {
        record.code_muni: record for record in ibge_records
    }
    
    logger.info(f"Loaded IBGE metadata for {len(ibge_by_code)} municipalities")
    
    # 5. Build coverage rows
    coverage_rows = []
    
    for code in all_codes:
        official_count = official_by_code.get(code, 0)
        arquivo_count = arquivo_by_code.get(code, 0)
        
        # Hide official 0 + Arquivo 0 (issue #183)
        if official_count == 0 and arquivo_count == 0:
            continue
        
        # Calculate coverage (None when official=0 to avoid divide-by-zero)
        if official_count > 0:
            coverage = round(arquivo_count / official_count, 2)
        else:
            coverage = None
        
        # Get IBGE metadata
        ibge = ibge_by_code.get(code)
        if not ibge:
            logger.warning(f"Municipality code {code} not found in IBGE data, skipping")
            continue
        
        coverage_rows.append({
            "code": code,
            "name": ibge.name_muni,
            "uf": ibge.abbrev_state,
            "official_victims": official_count,
            "arquivo_victims": arquivo_count,
            "coverage": coverage,
        })
    
    # 6. Sort by official_victims descending (spec requirement)
    coverage_rows.sort(key=lambda x: x["official_victims"], reverse=True)
    
    logger.info(f"Generated coverage table with {len(coverage_rows)} municipalities")
    
    return coverage_rows
