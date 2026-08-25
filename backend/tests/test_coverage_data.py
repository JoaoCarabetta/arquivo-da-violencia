"""Tests for coverage data aggregator (Arquivo vs Official violence statistics).

This module tests the coverage aggregator function that combines:
1. Official "mortes violentas intencionais" counts from Ministry of Justice VDE data
2. Arquivo victim counts from UniqueEvent (public incident filter)
3. Municipality metadata from IBGE population table

Window: 2025-09-01 through latest official month (complete months only).

Acceptance criteria from issue #176:
- Union of municipalities with official > 0 OR Arquivo > 0
- Coverage = Arquivo / official (not capped)
- Official 0 + Arquivo > 0 → row exists, coverage None
- Events without municipality_code → absent
- Non-Brazil events → absent
"""

import pytest
from datetime import datetime

from app.models.official_violence_data import OfficialViolenceCount
from app.models.unique_event import UniqueEvent
from app.models.ibge_population import IBGEPopulation
from app.services.coverage_data import get_coverage_data


@pytest.fixture
async def setup_coverage_fixture(async_session):
    """Load IBGE data, official counts, and Arquivo events for coverage tests."""
    
    # IBGE population data (municipalities with codes)
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
        IBGEPopulation(
            code_muni=3509502,
            code_state="35",
            name_muni="Campinas",
            name_state="São Paulo",
            abbrev_state="SP",
            population=1213792,
            year=2022
        ),
    ]
    for muni in municipalities:
        async_session.add(muni)
    
    # Official violence counts (mortes violentas intencionais)
    official_counts = [
        # São Paulo: 10 official victims in 2025-09
        OfficialViolenceCount(
            code_muni=3550308,
            year_month="2025-09",
            indicator="mortes_violentas_intencionais",
            victim_count=10,
            is_total=True,
            source="SINESP VDE"
        ),
        # Rio: 0 official victims in 2025-09
        OfficialViolenceCount(
            code_muni=3304557,
            year_month="2025-09",
            indicator="mortes_violentas_intencionais",
            victim_count=0,
            is_total=True,
            source="SINESP VDE"
        ),
        # Bauru: 10 official victims in 2025-09
        OfficialViolenceCount(
            code_muni=3505708,
            year_month="2025-09",
            indicator="mortes_violentas_intencionais",
            victim_count=10,
            is_total=True,
            source="SINESP VDE"
        ),
    ]
    for count in official_counts:
        async_session.add(count)
    
    # Arquivo unique events (public incident filter: homicidio, incident, victim_count <= 10)
    events = [
        # São Paulo: 4 victims (in window, has municipality_code)
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="BR",
            state="SP",
            city="São Paulo",
            municipality_code=3550308,
            event_date=datetime(2025, 9, 15),
            victim_count=4,
            latitude=-23.55052,
            longitude=-46.633308,
        ),
        # Rio: 3 victims (official 0, Arquivo > 0 case)
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="BR",
            state="RJ",
            city="Rio de Janeiro",
            municipality_code=3304557,
            event_date=datetime(2025, 9, 20),
            victim_count=3,
            latitude=-22.9068,
            longitude=-43.1729,
        ),
        # Bauru: 12 victims (coverage > 1 case)
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="BR",
            state="SP",
            city="Bauru",
            municipality_code=3505708,
            event_date=datetime(2025, 9, 25),
            victim_count=12,
            latitude=-22.3211,
            longitude=-49.0705,
        ),
        # Campinas: event without municipality_code (should be absent from coverage)
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="BR",
            state="SP",
            city="Campinas",
            municipality_code=None,  # Missing code
            event_date=datetime(2025, 9, 28),
            victim_count=5,
            latitude=-22.9056,
            longitude=-47.0608,
        ),
        # São Paulo: event before window (should be excluded)
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="BR",
            state="SP",
            city="São Paulo",
            municipality_code=3550308,
            event_date=datetime(2025, 8, 15),  # Before 2025-09
            victim_count=99,
            latitude=-23.55052,
            longitude=-46.633308,
        ),
        # Chile event (should be excluded - non-Brazil)
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="CL",
            state="RM",
            city="Santiago",
            municipality_code=None,
            event_date=datetime(2025, 9, 30),
            victim_count=10,
            latitude=-33.4489,
            longitude=-70.6693,
        ),
    ]
    for event in events:
        async_session.add(event)
    
    await async_session.commit()


@pytest.mark.asyncio
async def test_coverage_oficial_10_arquivo_4(async_session, setup_coverage_fixture):
    """
    Test case 1: Official 10, Arquivo 4 → coverage 0.4.
    
    São Paulo has 10 official victims and 4 Arquivo victims.
    Coverage = 4 / 10 = 0.4.
    """
    coverage = await get_coverage_data(async_session)
    
    # Find São Paulo row
    sp_row = next((r for r in coverage if r["code"] == 3550308), None)
    assert sp_row is not None, "São Paulo should be in coverage table"
    
    assert sp_row["code"] == 3550308
    assert sp_row["name"] == "São Paulo"
    assert sp_row["uf"] == "SP"
    assert sp_row["official_victims"] == 10
    assert sp_row["arquivo_victims"] == 4
    assert sp_row["coverage"] == 0.4


@pytest.mark.asyncio
async def test_coverage_oficial_0_arquivo_3(async_session, setup_coverage_fixture):
    """
    Test case 2: Official 0, Arquivo 3 → row exists, coverage None.
    
    Rio has 0 official victims but 3 Arquivo victims.
    Row should exist with coverage = None (not a divide-by-zero error).
    """
    coverage = await get_coverage_data(async_session)
    
    # Find Rio row
    rj_row = next((r for r in coverage if r["code"] == 3304557), None)
    assert rj_row is not None, "Rio should be in coverage table"
    
    assert rj_row["code"] == 3304557
    assert rj_row["name"] == "Rio de Janeiro"
    assert rj_row["uf"] == "RJ"
    assert rj_row["official_victims"] == 0
    assert rj_row["arquivo_victims"] == 3
    assert rj_row["coverage"] is None  # Not a divide-by-zero


@pytest.mark.asyncio
async def test_coverage_oficial_10_arquivo_12(async_session, setup_coverage_fixture):
    """
    Test case 3: Official 10, Arquivo 12 → coverage 1.2 (not capped).
    
    Bauru has 10 official victims and 12 Arquivo victims.
    Coverage = 12 / 10 = 1.2 (uncapped, shows over-coverage).
    """
    coverage = await get_coverage_data(async_session)
    
    # Find Bauru row
    bauru_row = next((r for r in coverage if r["code"] == 3505708), None)
    assert bauru_row is not None, "Bauru should be in coverage table"
    
    assert bauru_row["code"] == 3505708
    assert bauru_row["name"] == "Bauru"
    assert bauru_row["uf"] == "SP"
    assert bauru_row["official_victims"] == 10
    assert bauru_row["arquivo_victims"] == 12
    assert bauru_row["coverage"] == 1.2


@pytest.mark.asyncio
async def test_event_without_municipality_code_absent(async_session, setup_coverage_fixture):
    """
    Test case 4: Event without municipality_code → absent from coverage.
    
    Campinas event has municipality_code=None, so it should not appear
    in the coverage table.
    """
    coverage = await get_coverage_data(async_session)
    
    # Campinas should NOT be in coverage (no municipality_code)
    campinas_row = next((r for r in coverage if r["code"] == 3509502), None)
    assert campinas_row is None, "Campinas should be absent (no municipality_code)"


@pytest.mark.asyncio
async def test_non_brazil_event_absent(async_session, setup_coverage_fixture):
    """
    Test case 5: Non-Brazil event → absent from coverage.
    
    Chile event should not appear in the coverage table.
    """
    coverage = await get_coverage_data(async_session)
    
    # No Chile municipalities should be in coverage
    chile_rows = [r for r in coverage if r["uf"] not in {"SP", "RJ"}]
    assert len(chile_rows) == 0, "No Chile events should be in coverage"


@pytest.mark.asyncio
async def test_event_before_window_absent(async_session, setup_coverage_fixture):
    """
    Test case 6: Event date before 2025-09-01 → absent from Arquivo count.
    
    São Paulo has an event on 2025-08-15 (before window) with 99 victims.
    This should NOT be counted in the Arquivo victims for São Paulo.
    """
    coverage = await get_coverage_data(async_session)
    
    # Find São Paulo row
    sp_row = next((r for r in coverage if r["code"] == 3550308), None)
    assert sp_row is not None
    
    # Should only count the 4 victims from the 2025-09-15 event
    # NOT the 99 victims from the 2025-08-15 event
    assert sp_row["arquivo_victims"] == 4, "Should only count events >= 2025-09-01"


@pytest.mark.asyncio
async def test_coverage_default_sort_by_official_desc(async_session, setup_coverage_fixture):
    """
    Test that coverage data is sorted by official victims descending.
    
    Default sort should be official victims descending:
    - São Paulo: 10 official
    - Bauru: 10 official
    - Rio: 0 official
    """
    coverage = await get_coverage_data(async_session)
    
    # Should have 3 rows (São Paulo, Bauru, Rio)
    assert len(coverage) == 3
    
    # Sort should be by official victims descending
    # São Paulo and Bauru both have 10, Rio has 0
    # Within same count, order is undefined but stable
    official_counts = [r["official_victims"] for r in coverage]
    assert official_counts == sorted(official_counts, reverse=True), \
        "Should be sorted by official victims descending"
