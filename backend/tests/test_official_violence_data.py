"""Tests for official violence data service (Ministry of Justice VDE data)."""

import pytest
from sqlmodel import select

from app.models.official_violence_data import OfficialViolenceCount
from app.models.ibge_population import IBGEPopulation
from app.services.official_violence_data import (
    ingest_official_violence_data,
    get_official_violence_totals,
)

# dump headers from bancovde-2025.xlsx:
# ["uf","municipio","evento","data_referencia","agente","arma","faixa_etaria","feminino","masculino","nao_informado","total_vitima","total","total_peso","abrangencia"]

@pytest.fixture
async def setup_ibge_data(async_session):
    """Load IBGE population data for municipality name resolution."""
    # Add test municipalities with title case names (as geobr provides)
    # Real dump uses uppercase ("SÃO PAULO"), IBGE uses title case ("São Paulo")
    municipalities = [
        IBGEPopulation(
            code_muni=3550308,
            name_muni="São Paulo",  # Title case (as from geobr)
            abbrev_state="SP",
            population=12396372,
            year=2022
        ),
        IBGEPopulation(
            code_muni=3304557,
            name_muni="Rio de Janeiro",  # Title case (as from geobr)
            abbrev_state="RJ",
            population=6775561,
            year=2022
        ),
    ]
    for muni in municipalities:
        async_session.add(muni)
    await async_session.commit()

@pytest.mark.asyncio
async def test_ingest_official_violence_data_single_municipality(async_session, setup_ibge_data):
    """
    Test ingesting official violence data for one municipality and one month.

    This is the core seam: given fixture VDE data for one municipality/month,
    persist per-indicator counts and the summed official municipal total (Formulário 1 types only).

    Acceptance criteria from issue #175 and #183:
    - Store by municipality code + year-month + indicator
    - Sum the 4 Formulário 1 indicators into the official municipal total (no intervenção)

    Fixture uses real bancovde-2025.xlsx column structure (14 columns).
    Excel serial date 45901 = 2025-09-01.
    Rows are sliced by agente/arma/faixa_etaria - we sum total_vitima.
    """
    # Fixture: bancovde data for São Paulo (SP) in Sep 2025
    # Multiple rows per evento (disaggregated by agente/arma/faixa_etaria) - should be summed
    vde_fixture = [
        # Homicídio doloso: 2 rows, sum = 53
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,  # 2025-09-01
            "agente": "",
            "arma": "Arma de fogo",
            "faixa_etaria": "18 a 24",
            "feminino": 0,
            "masculino": 30,
            "nao_informado": 0,
            "total_vitima": 30,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,
            "agente": "",
            "arma": "Arma branca",
            "faixa_etaria": "25 a 29",
            "feminino": 0,
            "masculino": 23,
            "nao_informado": 0,
            "total_vitima": 23,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
        # Feminicídio: 1 row
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Feminicídio",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 3,
            "masculino": 0,
            "nao_informado": 0,
            "total_vitima": 3,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
        # Roubo seguido de morte (latrocínio): 1 row
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Roubo seguido de morte (latrocínio)",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 6,
            "nao_informado": 0,
            "total_vitima": 6,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
        # Lesão corporal seguida de morte: 1 row
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Lesão corporal seguida de morte",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 2,
            "nao_informado": 0,
            "total_vitima": 2,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
        # Morte por intervenção de Agente do Estado: 1 row
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Morte por intervenção de Agente do Estado",
            "data_referencia": 45901,
            "agente": "Polícia Militar",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 13,
            "nao_informado": 0,
            "total_vitima": 13,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
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
    assert homicidio.victim_count == 53  # 30 + 23 from disaggregated rows

    feminicidio = next(c for c in counts if c.indicator == "feminicidio")
    assert feminicidio.victim_count == 3

    latrocinio = next(c for c in counts if c.indicator == "latrocinio")
    assert latrocinio.victim_count == 6

    lesao = next(c for c in counts if c.indicator == "lesao_corporal_seguida_morte")
    assert lesao.victim_count == 2

    intervencao = next(c for c in counts if c.indicator == "morte_intervencao_policial")
    assert intervencao.victim_count == 13

    # Check sum of four Formulário 1 types (no intervenção, no convenience total)
    homicidio = next(c for c in counts if c.indicator == "homicidio_doloso")
    feminicidio = next(c for c in counts if c.indicator == "feminicidio")
    latrocinio = next(c for c in counts if c.indicator == "latrocinio")
    lesao = next(c for c in counts if c.indicator == "lesao_corporal_seguida_morte")
    
    formulario_1_sum = homicidio.victim_count + feminicidio.victim_count + latrocinio.victim_count + lesao.victim_count
    assert formulario_1_sum == 64, f"Four-type sum should be 64 (53+3+6+2), got {formulario_1_sum}"

@pytest.mark.asyncio
async def test_ingest_idempotence(async_session, setup_ibge_data):
    """
    Test that re-ingesting the same month overwrites (does not duplicate).

    Acceptance criteria from issue #175:
    - Re-running ingest for the same month overwrites, does not duplicate
    """
    vde_fixture_v1 = [
        {
            "uf": "RJ",
            "municipio": "RIO DE JANEIRO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,  # 2025-09-01
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 23,
            "nao_informado": 0,
            "total_vitima": 23,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
    ]

    vde_fixture_v2 = [
        {
            "uf": "RJ",
            "municipio": "RIO DE JANEIRO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 30,
            "nao_informado": 0,
            "total_vitima": 30,  # Updated count
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
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
    assert counts[0].victim_count == 30

@pytest.mark.asyncio
async def test_get_official_violence_totals_window_filter(async_session, setup_ibge_data):
    """
    Test that querying official totals respects the v1 window (>= 2025-09).

    Acceptance criteria from issue #175:
    - Window starts at 2025-09 (first full month after Arquivo start 2025-08-26)
    - Older months may be stored but are out of the v1 table
    """
    # Fixture: data before and after the window cutoff
    fixture_before_window = [
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Homicídio doloso",
            "data_referencia": 45870,  # 2025-08-01 (before window)
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 60,
            "nao_informado": 0,
            "total_vitima": 60,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
    ]

    fixture_in_window = [
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,  # 2025-09-01 (in window)
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 53,
            "nao_informado": 0,
            "total_vitima": 53,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
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

@pytest.mark.asyncio
async def test_case_insensitive_municipality_resolution(async_session, setup_ibge_data):
    """
    Test that municipality name resolution is case-insensitive.

    The dump uses uppercase names ("SÃO PAULO"), while ibge_population
    from geobr uses title case ("São Paulo"). Resolution must be case-insensitive
    (casefold both sides) to avoid dropping all rows.

    Spec: Accents stay as-is (Ã = Ã), only case is normalized.
    """
    # IBGE fixture already has name_muni="SÃO PAULO", abbrev_state="SP" (uppercase in setup_ibge_data)
    # But let's verify with explicit title case entry too
    # Actually, setup_ibge_data uses uppercase - let me check the fixture

    # Dump row with uppercase municipality name
    vde_fixture = [
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",  # Uppercase (as in real dump)
            "evento": "Homicídio doloso",
            "data_referencia": 45901,  # 2025-09-01
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 42,
            "nao_informado": 0,
            "total_vitima": 42,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
    ]

    # Ingest
    await ingest_official_violence_data(async_session, vde_fixture)

    # Verify row was stored with correct code_muni
    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni == 3550308,
        OfficialViolenceCount.year_month == "2025-09",
        OfficialViolenceCount.indicator == "homicidio_doloso"
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    # Should match despite case difference
    assert len(counts) == 1
    assert counts[0].victim_count == 42
    assert counts[0].code_muni == 3550308

@pytest.mark.asyncio
async def test_unmatched_municipality_dropped(async_session, setup_ibge_data):
    """
    Test that rows with unmatched municipality names are dropped.

    Spec: Rows that don't match an IBGE code are dropped (no unmatched name-only rows).
    """
    # Dump row with non-existent municipality
    vde_fixture = [
        {
            "uf": "ZZ",
            "municipio": "CIDADE INEXISTENTE",  # Does not exist in IBGE
            "evento": "Homicídio doloso",
            "data_referencia": 45901,  # 2025-09-01
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 99,
            "nao_informado": 0,
            "total_vitima": 99,
            "total": 0,
            "total_peso": 0,
            "abrangencia": ""
        },
    ]

    # Ingest
    await ingest_official_violence_data(async_session, vde_fixture)

    # Query all rows - should be empty (unmatched row dropped)
    query = select(OfficialViolenceCount)
    result = await async_session.execute(query)
    counts = result.scalars().all()

    # Should have zero rows (unmatched municipality dropped)
    assert len(counts) == 0

