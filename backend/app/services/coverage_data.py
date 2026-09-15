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

from collections import defaultdict
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

from app.models.official_violence_data import (
    OfficialRevision,
    OfficialSourceId,
    OfficialViolenceCount,
)
from app.models.unique_event import UniqueEvent
from app.models.ibge_population import IBGEPopulation
from app.services.public_filters import public_incident_criteria
from app.services.official_typology import formulario_1_indicators
from app.services.official_violence_data import BANCOVDE_WINDOW_START


# Coverage window: complete months from 2025-09 onwards
# (first full month after Arquivo start 2025-08-26)
COVERAGE_WINDOW_START = datetime(2025, 9, 1)


def get_formulario_1_types() -> list[str]:
    """
    Return the four Formulário 1 indicator types used in official municipal totals.

    NOTE: morte_intervencao_policial is NOT included in this list.
    """
    return formulario_1_indicators()


OfficialKey = Tuple[int, str, str]


async def _load_validador_official_by_municipality(
    session: AsyncSession,
    formulario_1_types: list[str],
    min_year_month: str,
) -> Tuple[Dict[int, int], Set[int], Dict[int, bool]]:
    """
    Load Validador official counts with consolidado-over-preliminar preference.

    For each municipality × month × indicator, use consolidado when present;
    otherwise fall back to preliminar. State SSP sources (rj, mg, sp) are excluded.

    Returns:
        official_by_code: summed victim counts per municipality
        official_published_codes: municipalities with any official row in window
        official_is_preliminar_by_code: True when any selected row used preliminar
    """
    official_query = select(
        OfficialViolenceCount.code_muni,
        OfficialViolenceCount.year_month,
        OfficialViolenceCount.indicator,
        OfficialViolenceCount.revision,
        OfficialViolenceCount.victim_count,
    ).where(
        OfficialViolenceCount.indicator.in_(formulario_1_types),
        OfficialViolenceCount.year_month >= min_year_month,
        OfficialViolenceCount.source_id == OfficialSourceId.VALIDADOR,
    )

    official_result = await session.execute(official_query)
    official_rows = official_result.all()

    by_key: Dict[OfficialKey, Dict[OfficialRevision, int]] = defaultdict(dict)
    for row in official_rows:
        key = (row.code_muni, row.year_month, row.indicator)
        by_key[key][row.revision] = row.victim_count

    official_by_code: Dict[int, int] = defaultdict(int)
    official_published_codes: Set[int] = set()
    official_is_preliminar_by_code: Dict[int, bool] = defaultdict(bool)

    for (code_muni, _year_month, _indicator), revisions in by_key.items():
        if OfficialRevision.CONSOLIDADO in revisions:
            victim_count = revisions[OfficialRevision.CONSOLIDADO]
            used_preliminar = False
        elif OfficialRevision.PRELIMINAR in revisions:
            victim_count = revisions[OfficialRevision.PRELIMINAR]
            used_preliminar = True
        else:
            continue

        official_by_code[code_muni] += victim_count
        official_published_codes.add(code_muni)
        if used_preliminar:
            official_is_preliminar_by_code[code_muni] = True

    return dict(official_by_code), official_published_codes, dict(official_is_preliminar_by_code)


async def get_coverage_data(
    session: AsyncSession,
    min_year_month: str = BANCOVDE_WINDOW_START,
    search: Optional[str] = None
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
        search: Optional search term to filter municipality names (case-insensitive)
    
    Returns:
        List of dicts with keys:
        - code: 7-digit IBGE municipal code
        - name: Municipality name
        - uf: State abbreviation (e.g. "SP", "RJ")
        - official_victims: Official municipal total count (Formulário 1 types only)
        - official_published: Boolean - True if official data exists (even if sum=0), False if no data
        - official_is_preliminar: Boolean - True when any month used preliminar because
          consolidado was absent for that municipality-month-indicator key
        - arquivo_victims: Arquivo victim count (public filter)
        - coverage: Arquivo / official ratio (None when official=0)
        
        Sorted by official_victims descending.
    
    Acceptance criteria:
    - Official 0 + Arquivo > 0 → row exists, coverage=None, official_published can be True or False
    - Official 0 + Arquivo 0 → row absent (hidden)
    - Official 10 + Arquivo 12 → coverage=1.2 (not capped)
    - Event without municipality_code → absent
    - Non-Brazil event → absent
    - Event before 2025-09-01 → absent from Arquivo count
    
    Issue #187: Three distinct empty marks require official_published flag to distinguish
    "not published" (official_published=False) from "published zero" (official_published=True, official_victims=0).
    """
    
    # 1. Get official counts (Formulário 1 types only) by municipality.
    # Validador source only; prefer consolidado, else preliminar with flag.
    formulario_1_types = get_formulario_1_types()

    official_by_code, official_published_codes, official_is_preliminar_by_code = (
        await _load_validador_official_by_municipality(
            session, formulario_1_types, min_year_month
        )
    )

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
        official_published = code in official_published_codes
        
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
            "official_published": official_published,
            "official_is_preliminar": official_is_preliminar_by_code.get(code, False),
            "arquivo_victims": arquivo_count,
            "coverage": coverage,
        })
    
    # 6. Sort by official_victims descending (spec requirement)
    coverage_rows.sort(key=lambda x: x["official_victims"], reverse=True)
    
    # 7. Apply search filter if provided (case-insensitive)
    if search:
        search_lower = search.lower()
        coverage_rows = [
            row for row in coverage_rows
            if search_lower in row["name"].lower()
        ]
    
    logger.info(f"Generated coverage table with {len(coverage_rows)} municipalities")
    
    return coverage_rows
