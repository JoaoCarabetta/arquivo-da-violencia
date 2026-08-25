"""
Tests for issue #187 acceptance criteria (agreed seams).

These tests validate that the coverage table implementation meets the spec requirements.
Tests should fail if the requirements are violated.
"""

import pytest
from datetime import datetime

from app.models.official_violence_data import OfficialViolenceCount
from app.models.unique_event import UniqueEvent
from app.models.ibge_population import IBGEPopulation
from app.services.coverage_data import get_coverage_data


@pytest.mark.asyncio
async def test_default_table_must_not_include_0_0_rows(async_session):
    """
    Issue #187 TDD seam: Default table must not include 0/0 rows.
    
    If this test fails, it means a municipality with official=0 and Arquivo=0
    is incorrectly appearing in the coverage table.
    """
    # Setup IBGE data
    municipalities = [
        IBGEPopulation(
            code_muni=3550308,
            code_state="35",
            name_muni="São Paulo",
            name_state="São Paulo",
            abbrev_state="SP",
            population=12396372,
            year=2022
        ),
        IBGEPopulation(
            code_muni=3304557,
            code_state="33",
            name_muni="Rio de Janeiro",
            name_state="Rio de Janeiro",
            abbrev_state="RJ",
            population=6775561,
            year=2022
        ),
    ]
    for muni in municipalities:
        async_session.add(muni)
    
    # São Paulo: has oficial data (10) and Arquivo data (5)
    async_session.add(OfficialViolenceCount(
        code_muni=3550308,
        year_month="2025-09",
        indicator="homicidio_doloso",
        victim_count=10,
        is_total=False,
        source="SINESP VDE"
    ))
    async_session.add(UniqueEvent(
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        country="BR",
        state="SP",
        city="São Paulo",
        municipality_code=3550308,
        event_date=datetime(2025, 9, 15),
        victim_count=5,
        latitude=-23.55052,
        longitude=-46.633308,
    ))
    
    # Rio: official=0 AND Arquivo=0 (should be hidden)
    # NO official counts, NO Arquivo events
    
    await async_session.commit()
    
    # Get coverage data
    coverage = await get_coverage_data(async_session)
    
    # Check that Rio (0/0) is NOT in the table
    rio_row = next((r for r in coverage if r["code"] == 3304557), None)
    assert rio_row is None, \
        "FAIL: 0/0 row (Rio) should be hidden from default table but was found"
    
    # Check that São Paulo is present
    sp_row = next((r for r in coverage if r["code"] == 3550308), None)
    assert sp_row is not None, "São Paulo should be in coverage table"


@pytest.mark.asyncio
async def test_official_only_gap_rows_must_be_present(async_session):
    """
    Issue #187 TDD seam: Official-only gap rows (official>0, Arquivo=0) must be present.
    
    If this test fails, it means a municipality with official>0 but Arquivo=0
    is incorrectly missing from the coverage table.
    """
    # Setup IBGE data
    municipality = IBGEPopulation(
        code_muni=3550308,
        code_state="35",
        name_muni="São Paulo",
        name_state="São Paulo",
        abbrev_state="SP",
        population=12396372,
        year=2022
    )
    async_session.add(municipality)
    
    # São Paulo: has oficial data (10) but NO Arquivo data (gap)
    async_session.add(OfficialViolenceCount(
        code_muni=3550308,
        year_month="2025-09",
        indicator="homicidio_doloso",
        victim_count=10,
        is_total=False,
        source="SINESP VDE"
    ))
    
    # NO Arquivo events for São Paulo
    
    await async_session.commit()
    
    # Get coverage data
    coverage = await get_coverage_data(async_session)
    
    # Check that São Paulo (official>0, Arquivo=0) IS in the table
    sp_row = next((r for r in coverage if r["code"] == 3550308), None)
    assert sp_row is not None, \
        "FAIL: Official-only gap row (official>0, Arquivo=0) should be present but was not found"
    assert sp_row["official_victims"] == 10
    assert sp_row["arquivo_victims"] == 0
    assert sp_row["coverage"] is None


@pytest.mark.asyncio
async def test_search_rio_de_janeiro_must_match(async_session):
    """
    Issue #187 TDD seam: Search for "Rio de Janeiro" must match that municipality.
    
    Uses the coverage API's q= parameter to test actual search path.
    If this test fails, the API search is broken or Rio de Janeiro is not findable.
    """
    # Setup IBGE data
    municipalities = [
        IBGEPopulation(
            code_muni=3550308,
            code_state="35",
            name_muni="São Paulo",
            name_state="São Paulo",
            abbrev_state="SP",
            population=12396372,
            year=2022
        ),
        IBGEPopulation(
            code_muni=3304557,
            code_state="33",
            name_muni="Rio de Janeiro",
            name_state="Rio de Janeiro",
            abbrev_state="RJ",
            population=6775561,
            year=2022
        ),
        IBGEPopulation(
            code_muni=3505708,
            code_state="35",
            name_muni="Bauru",
            name_state="São Paulo",
            abbrev_state="SP",
            population=379297,
            year=2022
        ),
    ]
    for muni in municipalities:
        async_session.add(muni)
    
    # Add data for all municipalities so they appear in coverage
    for code in [3550308, 3304557, 3505708]:
        async_session.add(OfficialViolenceCount(
            code_muni=code,
            year_month="2025-09",
            indicator="homicidio_doloso",
            victim_count=5,
            is_total=False,
            source="SINESP VDE"
        ))
    
    await async_session.commit()
    
    # Test the actual API search path with q= parameter
    coverage_all = await get_coverage_data(async_session)
    coverage_filtered = await get_coverage_data(async_session, search="Rio de Janeiro")
    
    # Verify unfiltered returns all 3 municipalities
    assert len(coverage_all) == 3, "Should have 3 municipalities without search"
    
    # Verify filtered returns only Rio de Janeiro
    assert len(coverage_filtered) == 1, \
        "FAIL: Search for 'Rio de Janeiro' must return exactly 1 match"
    
    rio_row = coverage_filtered[0]
    assert rio_row["name"] == "Rio de Janeiro", \
        "FAIL: Search result must be Rio de Janeiro"
    assert rio_row["code"] == 3304557
    
    # Verify case-insensitive search works
    coverage_lower = await get_coverage_data(async_session, search="rio de janeiro")
    assert len(coverage_lower) == 1, "Search must be case-insensitive"
    assert coverage_lower[0]["code"] == 3304557
