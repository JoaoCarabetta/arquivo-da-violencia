"""Tests for official violence data service (Ministry of Justice VDE data)."""

import inspect
from pathlib import Path

import pytest
from sqlmodel import select

from app.models.official_violence_data import (
    OfficialRevision,
    OfficialSourceId,
    OfficialViolenceCount,
)
from app.models.ibge_population import IBGEPopulation
from app.services.official_violence_data import (
    BANCOVDE_WINDOW_START,
    bancovde_govbr_url,
    ingest_official_violence_data,
    get_official_violence_totals,
    parse_bancovde_workbook,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "bancovde"
BANCOVDE_SLICE_XLSX = FIXTURES_DIR / "bancovde_slice_2025.xlsx"


def test_get_official_violence_totals_default_window_uses_bancovde_constant():
    """Issue #241: default min_year_month should reference BANCOVDE_WINDOW_START."""
    sig = inspect.signature(get_official_violence_totals)
    assert sig.parameters["min_year_month"].default == BANCOVDE_WINDOW_START


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

    # Should have 5 indicator rows (no convenience total)
    assert len(counts) == 5, f"Expected 5 rows (4 Formulário 1 types + intervenção), got {len(counts)}"

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


@pytest.mark.asyncio
async def test_unmapped_evento_skipped(async_session, setup_ibge_data):
    """Unmapped naturezas are skipped during ingest (issue #239)."""
    vde_fixture = [
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Suicídio",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 5,
            "nao_informado": 0,
            "total_vitima": 5,
            "total": 0,
            "total_peso": 0,
            "abrangencia": "",
        },
    ]

    await ingest_official_violence_data(async_session, vde_fixture)

    query = select(OfficialViolenceCount)
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert len(counts) == 0


@pytest.mark.asyncio
async def test_source_revision_uniqueness(async_session, setup_ibge_data):
    """
    Same municipality × month × indicator with different source_id or revision
    creates separate rows (issue #238).
    """
    vde_fixture = [
        {
            "uf": "SP",
            "municipio": "SÃO PAULO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 10,
            "nao_informado": 0,
            "total_vitima": 10,
            "total": 0,
            "total_peso": 0,
            "abrangencia": "",
        },
    ]

    await ingest_official_violence_data(
        async_session,
        vde_fixture,
        source_id=OfficialSourceId.VALIDADOR,
        revision=OfficialRevision.CONSOLIDADO,
    )
    await ingest_official_violence_data(
        async_session,
        vde_fixture,
        source_id=OfficialSourceId.RJ,
        revision=OfficialRevision.CONSOLIDADO,
    )
    await ingest_official_violence_data(
        async_session,
        vde_fixture,
        source_id=OfficialSourceId.VALIDADOR,
        revision=OfficialRevision.PRELIMINAR,
    )

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni == 3550308,
        OfficialViolenceCount.year_month == "2025-09",
        OfficialViolenceCount.indicator == "homicidio_doloso",
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert len(counts) == 3
    keys = {(c.source_id, c.revision) for c in counts}
    assert keys == {
        (OfficialSourceId.VALIDADOR, OfficialRevision.CONSOLIDADO),
        (OfficialSourceId.RJ, OfficialRevision.CONSOLIDADO),
        (OfficialSourceId.VALIDADOR, OfficialRevision.PRELIMINAR),
    }


@pytest.mark.asyncio
async def test_five_key_upsert(async_session, setup_ibge_data):
    """
    Re-ingesting with the same 5-key tuple updates victim_count instead of duplicating.
    """
    vde_fixture_v1 = [
        {
            "uf": "RJ",
            "municipio": "RIO DE JANEIRO",
            "evento": "Homicídio doloso",
            "data_referencia": 45901,
            "agente": "",
            "arma": "",
            "faixa_etaria": "",
            "feminino": 0,
            "masculino": 15,
            "nao_informado": 0,
            "total_vitima": 15,
            "total": 0,
            "total_peso": 0,
            "abrangencia": "",
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
            "masculino": 20,
            "nao_informado": 0,
            "total_vitima": 20,
            "total": 0,
            "total_peso": 0,
            "abrangencia": "",
        },
    ]

    await ingest_official_violence_data(
        async_session,
        vde_fixture_v1,
        source_id=OfficialSourceId.SP,
        revision=OfficialRevision.PRELIMINAR,
    )
    await ingest_official_violence_data(
        async_session,
        vde_fixture_v2,
        source_id=OfficialSourceId.SP,
        revision=OfficialRevision.PRELIMINAR,
    )

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni == 3304557,
        OfficialViolenceCount.year_month == "2025-09",
        OfficialViolenceCount.indicator == "homicidio_doloso",
        OfficialViolenceCount.source_id == OfficialSourceId.SP,
        OfficialViolenceCount.revision == OfficialRevision.PRELIMINAR,
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert len(counts) == 1
    assert counts[0].victim_count == 20


def test_bancovde_govbr_url_uses_portal_not_ckan():
    """Ingest path targets the working gov.br portal (issue #240)."""
    url = bancovde_govbr_url(2025)
    assert "gov.br/mj" in url
    assert "bancovde-2025.xlsx" in url
    assert "dados.mj" not in url


def test_parse_bancovde_workbook_filters_window_from_fixture():
    """Parse fixture xlsx without network; window starts at 2025-09."""
    assert BANCOVDE_SLICE_XLSX.exists(), "Run fixture generator or commit bancovde_slice_2025.xlsx"

    rows = parse_bancovde_workbook(
        BANCOVDE_SLICE_XLSX.read_bytes(),
        year=2025,
        since_year_month=BANCOVDE_WINDOW_START,
    )

    # 9 source rows in fixture; 1 is Aug 2025 (45870) → filtered out
    assert len(rows) == 8

    from app.services.official_violence_data import _excel_serial_to_year_month

    parsed_months = sorted(
        {_excel_serial_to_year_month(float(r["data_referencia"])) for r in rows}
    )
    assert parsed_months == ["2025-09", "2025-10"]
    assert all(
        _excel_serial_to_year_month(float(r["data_referencia"])) >= BANCOVDE_WINDOW_START
        for r in rows
    )


@pytest.mark.asyncio
async def test_ingest_from_bancovde_xlsx_fixture(async_session, setup_ibge_data):
    """End-to-end ingest→store from fixture workbook slice (issue #240)."""
    rows = parse_bancovde_workbook(
        BANCOVDE_SLICE_XLSX.read_bytes(),
        year=2025,
        since_year_month=BANCOVDE_WINDOW_START,
    )

    await ingest_official_violence_data(
        async_session,
        rows,
        source_id=OfficialSourceId.VALIDADOR,
        revision=OfficialRevision.CONSOLIDADO,
    )

    query = select(OfficialViolenceCount).order_by(
        OfficialViolenceCount.code_muni,
        OfficialViolenceCount.year_month,
        OfficialViolenceCount.indicator,
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    sp_sep = [
        c
        for c in counts
        if c.code_muni == 3550308 and c.year_month == "2025-09"
    ]
    assert len(sp_sep) == 5  # 4 Formulário 1 + intervenção

    homicidio = next(c for c in sp_sep if c.indicator == "homicidio_doloso")
    assert homicidio.victim_count == 53  # 30 + 23

    intervencao = next(
        c for c in sp_sep if c.indicator == "morte_intervencao_policial"
    )
    assert intervencao.victim_count == 13

    formulario_1_sum = sum(
        c.victim_count
        for c in sp_sep
        if c.indicator
        in {
            "homicidio_doloso",
            "feminicidio",
            "latrocinio",
            "lesao_corporal_seguida_morte",
        }
    )
    assert formulario_1_sum == 64

    rj_oct = next(
        c
        for c in counts
        if c.code_muni == 3304557
        and c.year_month == "2025-10"
        and c.indicator == "homicidio_doloso"
    )
    assert rj_oct.victim_count == 40


@pytest.mark.asyncio
async def test_preliminar_and_consolidado_from_same_fixture(async_session, setup_ibge_data):
    """
    Workbook has no revision column; both stages persist via ingest revision kwarg.

    Same bancovde snapshot ingested twice with different revision values creates
    separate rows (issue #240 acceptance #4).
    """
    rows = parse_bancovde_workbook(
        BANCOVDE_SLICE_XLSX.read_bytes(),
        year=2025,
        since_year_month=BANCOVDE_WINDOW_START,
    )

    prelim_rows = [
        {
            **row,
            "total_vitima": int(float(row["total_vitima"])) + 1
            if row.get("evento") == "Homicídio doloso" and row.get("uf") == "SP"
            else row["total_vitima"],
        }
        for row in rows
    ]

    await ingest_official_violence_data(
        async_session,
        prelim_rows,
        source_id=OfficialSourceId.VALIDADOR,
        revision=OfficialRevision.PRELIMINAR,
    )
    await ingest_official_violence_data(
        async_session,
        rows,
        source_id=OfficialSourceId.VALIDADOR,
        revision=OfficialRevision.CONSOLIDADO,
    )

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.code_muni == 3550308,
        OfficialViolenceCount.year_month == "2025-09",
        OfficialViolenceCount.indicator == "homicidio_doloso",
        OfficialViolenceCount.source_id == OfficialSourceId.VALIDADOR,
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert len(counts) == 2
    by_revision = {c.revision: c.victim_count for c in counts}
    assert by_revision[OfficialRevision.PRELIMINAR] == 55  # 31 + 24 from bumped rows
    assert by_revision[OfficialRevision.CONSOLIDADO] == 53

    prelim_totals = await get_official_violence_totals(
        async_session,
        code_munis=[3550308],
        min_year_month=BANCOVDE_WINDOW_START,
        revision=OfficialRevision.PRELIMINAR,
    )
    consol_totals = await get_official_violence_totals(
        async_session,
        code_munis=[3550308],
        min_year_month=BANCOVDE_WINDOW_START,
        revision=OfficialRevision.CONSOLIDADO,
    )
    assert prelim_totals[0]["victim_count"] == 66  # 55 + 3 + 6 + 2
    assert consol_totals[0]["victim_count"] == 64

