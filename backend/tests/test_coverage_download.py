"""Tests for coverage download endpoint (issue #187)."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import get_session
from app.models.ibge_population import IBGEPopulation
from app.models.official_violence_data import OfficialViolenceCount


@pytest.mark.asyncio
async def test_coverage_download_includes_all_municipalities(async_session):
    """
    Test /api/public/stats/coverage/download endpoint.
    
    Issue #187 acceptance: Download must contain the official universe
    (all IBGE municipalities) including those with official=0,
    labeled as 'oficial'.
    """
    # Setup: Add some IBGE municipalities
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
    
    # Add official data for only some municipalities (São Paulo and Rio)
    official_counts = [
        OfficialViolenceCount(
            code_muni=3550308,
            year_month="2025-09",
            indicator="homicidio_doloso",
            victim_count=10,
            is_total=False,
            source="SINESP VDE"
        ),
        OfficialViolenceCount(
            code_muni=3304557,
            year_month="2025-09",
            indicator="feminicidio",
            victim_count=5,
            is_total=False,
            source="SINESP VDE"
        ),
    ]
    for count in official_counts:
        async_session.add(count)
    
    await async_session.commit()
    
    # Override dependency
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    # Call download endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats/coverage/download")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    
    # Parse CSV
    content = response.text
    lines = content.strip().split('\n')
    
    # Check header
    assert lines[0] == "code,name,uf,oficial"
    
    # Check that all municipalities are present
    rows = [line.split(',') for line in lines[1:]]
    assert len(rows) == 3, "Should have all 3 IBGE municipalities"
    
    # Check São Paulo row (has official data)
    sp_row = [r for r in rows if r[0] == '3550308'][0]
    assert sp_row[1] == "São Paulo"
    assert sp_row[2] == "SP"
    assert sp_row[3] == "10"
    
    # Check Rio row (has official data)
    rj_row = [r for r in rows if r[0] == '3304557'][0]
    assert rj_row[1] == "Rio de Janeiro"
    assert rj_row[2] == "RJ"
    assert rj_row[3] == "5"
    
    # Check Bauru row (no official data, should have 0)
    bauru_row = [r for r in rows if r[0] == '3505708'][0]
    assert bauru_row[1] == "Bauru"
    assert bauru_row[2] == "SP"
    assert bauru_row[3] == "0", "Bauru should have 0 oficial (not filtered out)"
    
    # Verify sort order (by oficial descending)
    oficial_values = [int(r[3]) for r in rows]
    assert oficial_values == sorted(oficial_values, reverse=True), \
        "Should be sorted by oficial descending"


@pytest.mark.asyncio
async def test_download_labels_column_as_oficial(async_session):
    """
    Test that download CSV uses 'oficial' column name, not 'Arquivo'.
    
    Issue #187: Download should be labeled as official data, not Arquivo coverage.
    """
    # Setup minimal data
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
    await async_session.commit()
    
    # Override dependency
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    # Call download endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats/coverage/download")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    
    # Parse CSV header
    content = response.text
    header = content.strip().split('\n')[0]
    
    # Verify column name
    assert "oficial" in header, "CSV should have 'oficial' column"
    assert "arquivo" not in header.lower(), "CSV should NOT have 'arquivo' column"
    assert header == "code,name,uf,oficial", "Header should match expected format"
