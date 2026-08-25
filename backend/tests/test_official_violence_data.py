"""Tests for official violence data service (Ministry of Justice VDE data)."""

import pytest
from sqlmodel import select

from app.models.official_violence_data import OfficialViolenceCount
from app.services.official_violence_data import (
    ingest_official_violence_data,
    get_official_violence_totals,
)


@pytest.mark.asyncio
async def test_ingest_official_violence_data_single_municipality(async_session):
    """
    Test ingesting official violence data for one municipality and one month.
    
    This is the core seam: given fixture VDE data for one municipality/month,
    persist per-indicator counts and the summed mortes_violentas_intencionais total.
    
    Acceptance criteria from issue 175:
    - Store by municipality code + year-month + indicator
    - Sum the 5 indicators into mortes_violentas_intencionais total
    """
    # Fixture: VDE Formulário 1 data for São Paulo (3550308) in Sep 2025
    # Realistic column structure from Ministry of Justice VDE dump
    vde_fixture = [
        {
            "mes_ano": "09/2025",
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Homicídio Doloso",
            "vitimas_masculinas": 45,
            "vitimas_femininas": 8,
            "vitimas_nao_identificadas": 0,
        },
        {
            "mes_ano": "09/2025",
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Feminicídio",
            "vitimas_masculinas": 0,
            "vitimas_femininas": 3,
            "vitimas_nao_identificadas": 0,
        },
        {
            "mes_ano": "09/2025",
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Roubo Seguido de Morte (Latrocínio)",
            "vitimas_masculinas": 5,
            "vitimas_femininas": 1,
            "vitimas_nao_identificadas": 0,
        },
        {
            "mes_ano": "09/2025",
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Lesão Corporal Seguida de Morte",
            "vitimas_masculinas": 2,
            "vitimas_femininas": 0,
            "vitimas_nao_identificadas": 0,
        },
        {
            "mes_ano": "09/2025",
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Morte Decorrente de Intervenção Policial",
            "vitimas_masculinas": 12,
            "vitimas_femininas": 1,
            "vitimas_nao_identificadas": 0,
        },
    ]
    
    # Ingest
    await ingest_official_violence_data(async_session, vde_fixture)
    
    # Verify per-indicator counts were stored
    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni == 3550308,
        OfficialViolenceCount.year_month == "2025-09"
    ).order_by(OfficialViolenceCount.indicator)
    
    result = await async_session.execute(query)
    counts = result.scalars().all()
    
    # Should have 5 indicator rows + 1 summed total row
    assert len(counts) == 6, f"Expected 6 rows (5 indicators + 1 total), got {len(counts)}"
    
    # Check individual indicators
    homicidio = next(c for c in counts if c.indicator == "homicidio_doloso")
    assert homicidio.victim_count == 53  # 45 + 8 + 0
    
    feminicidio = next(c for c in counts if c.indicator == "feminicidio")
    assert feminicidio.victim_count == 3
    
    latrocinio = next(c for c in counts if c.indicator == "latrocinio")
    assert latrocinio.victim_count == 6
    
    lesao = next(c for c in counts if c.indicator == "lesao_corporal_seguida_morte")
    assert lesao.victim_count == 2
    
    intervencao = next(c for c in counts if c.indicator == "morte_intervencao_policial")
    assert intervencao.victim_count == 13
    
    # Check summed total (mortes violentas intencionais)
    total = next(c for c in counts if c.indicator == "mortes_violentas_intencionais")
    assert total.victim_count == 77  # 53 + 3 + 6 + 2 + 13
    assert total.is_total is True


@pytest.mark.asyncio
async def test_ingest_idempotence(async_session):
    """
    Test that re-ingesting the same month overwrites (does not duplicate).
    
    Acceptance criteria from issue 175:
    - Re-running ingest for the same month overwrites, does not duplicate
    """
    vde_fixture_v1 = [
        {
            "mes_ano": "09/2025",
            "uf": "RJ",
            "cod_municipio": "3304557",
            "municipio": "Rio de Janeiro",
            "tipo_crime": "Homicídio Doloso",
            "vitimas_masculinas": 20,
            "vitimas_femininas": 3,
            "vitimas_nao_identificadas": 0,
        },
    ]
    
    vde_fixture_v2 = [
        {
            "mes_ano": "09/2025",
            "uf": "RJ",
            "cod_municipio": "3304557",
            "municipio": "Rio de Janeiro",
            "tipo_crime": "Homicídio Doloso",
            "vitimas_masculinas": 25,  # Updated count
            "vitimas_femininas": 5,    # Updated count
            "vitimas_nao_identificadas": 0,
        },
    ]
    
    # First ingest
    await ingest_official_violence_data(async_session, vde_fixture_v1)
    
    # Second ingest (same month, updated data)
    await ingest_official_violence_data(async_session, vde_fixture_v2)
    
    # Query results
    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni == 3304557,
        OfficialViolenceCount.year_month == "2025-09",
        OfficialViolenceCount.indicator == "homicidio_doloso"
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()
    
    # Should have exactly 1 row (not duplicated)
    assert len(counts) == 1
    # Should have the updated values
    assert counts[0].victim_count == 30  # 25 + 5


@pytest.mark.asyncio
async def test_get_official_violence_totals_window_filter(async_session):
    """
    Test that querying official totals respects the v1 window (>= 2025-09).
    
    Acceptance criteria from issue 175:
    - Window starts at 2025-09 (first full month after Arquivo start 2025-08-26)
    - Older months may be stored but are out of the v1 table
    """
    # Fixture: data before and after the window cutoff
    fixture_before_window = [
        {
            "mes_ano": "08/2025",  # Before window
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Homicídio Doloso",
            "vitimas_masculinas": 50,
            "vitimas_femininas": 10,
            "vitimas_nao_identificadas": 0,
        },
    ]
    
    fixture_in_window = [
        {
            "mes_ano": "09/2025",  # In window
            "uf": "SP",
            "cod_municipio": "3550308",
            "municipio": "São Paulo",
            "tipo_crime": "Homicídio Doloso",
            "vitimas_masculinas": 45,
            "vitimas_femininas": 8,
            "vitimas_nao_identificadas": 0,
        },
    ]
    
    # Ingest both
    await ingest_official_violence_data(async_session, fixture_before_window)
    await ingest_official_violence_data(async_session, fixture_in_window)
    
    # Query with window filter
    totals = await get_official_violence_totals(
        async_session,
        code_munis=[3550308],
        min_year_month="2025-09"  # Window starts here
    )
    
    # Should only return data >= 2025-09
    assert len(totals) == 1
    assert totals[0]["code_muni"] == 3550308
    assert totals[0]["year_month"] == "2025-09"
    # Should NOT include the August data
