"""Tests for São Paulo SSP resolução 160 monthly adapter (issue #244).

Seam: SSP-SP municipality × month extract (NOT raw BO) → OfficialViolenceCount
(source_id=sp, revision from `revisao`) → coverage reader keeps Validador,
RJ, MG, and SP as distinct columns.

Live source (HTML table, natureza × months; unpivoted here to long CSV):
https://www.ssp.sp.gov.br/estatistica/dados-mensais
Resolução SSP 160/2001. Website may publish before Diário Oficial
(preliminar) and later rectify (consolidado).
"""

from datetime import datetime
from pathlib import Path

import pytest
from sqlmodel import select

from app.models.ibge_population import IBGEPopulation
from app.models.official_violence_data import (
    OfficialRevision,
    OfficialSourceId,
    OfficialViolenceCount,
)
from app.models.unique_event import UniqueEvent
from app.services.coverage_data import get_coverage_data
from app.services.official_typology import map_natureza
from app.services.ssp_sp import (
    SP_LABEL_TO_NATUREZA,
    SSP_SP_PORTAL_URL,
    ingest_ssp_sp_rows,
    parse_ssp_sp_csv,
    revision_from_ssp,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ssp_sp_resolucao160_mensal.csv"

SAO_PAULO = 3550308
BAURU = 3505708
RIO = 3304557
BELO_HORIZONTE = 3106200

SP_COVERAGE_KEYS = ("sp_victims", "sp_published", "sp_preliminar")
STATE_COVERAGE_KEYS = (
    "rj_victims",
    "rj_published",
    "rj_preliminar",
    "mg_victims",
    "mg_published",
    "mg_preliminar",
    *SP_COVERAGE_KEYS,
)


@pytest.fixture
async def setup_sp_ibge(async_session):
    municipalities = [
        IBGEPopulation(
            code_muni=SAO_PAULO,
            name_muni="São Paulo",
            abbrev_state="SP",
            population=12396372,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=BAURU,
            name_muni="Bauru",
            abbrev_state="SP",
            population=379297,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=RIO,
            name_muni="Rio de Janeiro",
            abbrev_state="RJ",
            population=6775561,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=BELO_HORIZONTE,
            name_muni="Belo Horizonte",
            abbrev_state="MG",
            population=2521564,
            year=2022,
        ),
    ]
    for muni in municipalities:
        async_session.add(muni)
    await async_session.commit()


def test_source_url_points_at_ssp_dados_mensais_not_bo():
    assert "ssp.sp.gov.br/estatistica/dados-mensais" in SSP_SP_PORTAL_URL
    assert "transparenciassp" not in SSP_SP_PORTAL_URL


@pytest.mark.parametrize(
    "value,expected",
    [
        ("preliminar", OfficialRevision.PRELIMINAR),
        ("parcial", OfficialRevision.PRELIMINAR),
        ("1", OfficialRevision.PRELIMINAR),
        ("consolidado", OfficialRevision.CONSOLIDADO),
        ("2", OfficialRevision.CONSOLIDADO),
        ("", OfficialRevision.CONSOLIDADO),
    ],
)
def test_revision_from_ssp(value, expected):
    assert revision_from_ssp(value) == expected


def test_normalize_strips_ordinal_before_alias_lookup():
    """'Nº' must not NFKC into 'No' (Unicode ordinal compatibility map)."""
    from app.services.ssp_sp import _SP_LABEL_ALIASES, _normalize_sp_label

    normalized = _normalize_sp_label("Nº DE VÍTIMAS EM HOMICÍDIO DOLOSO (3)")
    assert normalized == "n de vítimas em homicídio doloso"
    assert normalized in _SP_LABEL_ALIASES


def test_sp_label_aliases_go_through_shared_map_natureza():
    """Thin SP normalizer only; typology stays in map_natureza (#239)."""
    expected = {
        "Nº DE VÍTIMAS EM HOMICÍDIO DOLOSO (3)": ("bag", "homicidio_doloso"),
        "HOMICÍDIO DOLOSO (2)": ("bag", "homicidio_doloso"),
        "Nº DE VÍTIMAS EM LATROCÍNIO": ("bag", "latrocinio"),
        "LESÃO CORPORAL SEGUIDA DE MORTE": ("bag", "lesao_corporal_seguida_morte"),
        "FEMINICÍDIO": ("bag", "feminicidio"),
        "Nº DE VÍTIMAS EM HOMICÍDIO DECORRENTE DE INTERVENÇÃO POLICIAL": (
            "extra",
            "morte_intervencao_policial",
        ),
    }
    for label, (kind, indicator) in expected.items():
        natureza = SP_LABEL_TO_NATUREZA[label]
        mapped = map_natureza(natureza)
        assert mapped["kind"] == kind
        assert mapped["indicator"] == indicator


def test_parse_fixture_maps_bag_skips_unmapped_prefers_victims_and_window():
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_ssp_sp_csv(text, since="2025-09")

    assert all(r["year_month"] >= "2025-09" for r in records)
    assert not any(r["year_month"] == "2025-08" for r in records)

    indicators = {r["indicator"] for r in records}
    assert "homicidio_doloso" in indicators
    assert "latrocinio" in indicators
    assert "lesao_corporal_seguida_morte" in indicators
    assert "feminicidio" in indicators
    assert "morte_intervencao_policial" in indicators
    assert "tentativa_homicidio" not in indicators
    assert "furto_veiculo" not in indicators

    sp_sep = [
        r for r in records if r["code_muni"] == SAO_PAULO and r["year_month"] == "2025-09"
    ]
    by_ind = {r["indicator"]: r for r in sp_sep}
    # Victim row 80 wins over occurrence 75 — no double count
    assert by_ind["homicidio_doloso"]["victim_count"] == 80
    assert by_ind["homicidio_doloso"]["kind"] == "bag"
    assert by_ind["homicidio_doloso"]["revision"] == OfficialRevision.CONSOLIDADO
    # Latrocínio occurrence 2 + victims 2 → keep 2, not 4
    assert by_ind["latrocinio"]["victim_count"] == 2
    assert by_ind["lesao_corporal_seguida_morte"]["victim_count"] == 1
    assert by_ind["feminicidio"]["victim_count"] == 4
    assert by_ind["morte_intervencao_policial"]["victim_count"] == 10
    assert by_ind["morte_intervencao_policial"]["kind"] == "extra"

    sp_oct = [
        r
        for r in records
        if r["code_muni"] == SAO_PAULO and r["year_month"] == "2025-10"
    ]
    assert sp_oct
    assert all(r["revision"] == OfficialRevision.PRELIMINAR for r in sp_oct)


@pytest.mark.asyncio
async def test_ingest_fixture_writes_source_id_sp(async_session, setup_sp_ibge):
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_ssp_sp_csv(text, since="2025-09")
    await ingest_ssp_sp_rows(async_session, records)

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.source_id == OfficialSourceId.SP,
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert counts
    assert all(c.source_id == OfficialSourceId.SP for c in counts)
    assert all("SSP-SP" in c.source for c in counts)

    sp_sep_hd = next(
        c
        for c in counts
        if c.code_muni == SAO_PAULO
        and c.year_month == "2025-09"
        and c.indicator == "homicidio_doloso"
    )
    assert sp_sep_hd.victim_count == 80
    assert sp_sep_hd.revision == OfficialRevision.CONSOLIDADO

    sp_oct_hd = next(
        c
        for c in counts
        if c.code_muni == SAO_PAULO
        and c.year_month == "2025-10"
        and c.indicator == "homicidio_doloso"
    )
    assert sp_oct_hd.victim_count == 15
    assert sp_oct_hd.revision == OfficialRevision.PRELIMINAR

    assert not any(
        c.indicator in {"tentativa_homicidio", "furto_veiculo"} for c in counts
    )
    assert not any(c.year_month == "2025-08" for c in counts)


@pytest.mark.asyncio
async def test_ingest_unmapped_natureza_not_stored(async_session, setup_sp_ibge):
    records = [
        {
            "code_muni": SAO_PAULO,
            "year_month": "2025-09",
            "natureza": "Suicídio",
            "indicator": None,
            "kind": "unmapped",
            "victim_count": 9,
            "revision": OfficialRevision.CONSOLIDADO,
        }
    ]
    await ingest_ssp_sp_rows(async_session, records)

    result = await async_session.execute(select(OfficialViolenceCount))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_coverage_sp_column_distinct_from_validador(async_session, setup_sp_ibge):
    """SP bag is its own series; never summed into official_victims (#244 / #237)."""
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.VALIDADOR,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=10,
            is_total=False,
            source="SINESP VDE",
        )
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=RIO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.VALIDADOR,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=6,
            is_total=False,
            source="SINESP VDE",
        )
    )
    async_session.add(
        UniqueEvent(
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            country="BR",
            state="SP",
            city="São Paulo",
            municipality_code=SAO_PAULO,
            event_date=datetime(2025, 9, 15),
            victim_count=3,
            latitude=-23.5505,
            longitude=-46.6333,
        )
    )
    await async_session.commit()

    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_ssp_sp_csv(text, since="2025-09")
    await ingest_ssp_sp_rows(async_session, records)

    coverage = await get_coverage_data(async_session)
    sp = next(r for r in coverage if r["code"] == SAO_PAULO)

    assert sp["official_victims"] == 10
    # Bag: Sep consolidado 80+2+1+4=87 plus Oct preliminar 15 → 102
    # Extra (intervenção) excluded from both bag totals
    assert sp["sp_victims"] == 102
    assert sp["sp_published"] is True
    assert sp["arquivo_victims"] == 3
    assert sp["rj_victims"] == 0
    assert sp["mg_victims"] == 0

    rio = next(r for r in coverage if r["code"] == RIO)
    assert rio["official_victims"] == 6
    assert rio["sp_victims"] == 0
    assert rio["sp_published"] is False

    bauru = next(r for r in coverage if r["code"] == BAURU)
    assert bauru["official_victims"] == 0
    assert bauru["sp_victims"] == 5
    assert bauru["sp_published"] is True


@pytest.mark.asyncio
async def test_coverage_sp_prefers_consolidado_over_preliminar(
    async_session, setup_sp_ibge
):
    for revision, count in (
        (OfficialRevision.PRELIMINAR, 50),
        (OfficialRevision.CONSOLIDADO, 40),
    ):
        async_session.add(
            OfficialViolenceCount(
                code_muni=SAO_PAULO,
                year_month="2025-09",
                indicator="homicidio_doloso",
                source_id=OfficialSourceId.SP,
                revision=revision,
                victim_count=count,
                is_total=False,
                source="SSP-SP",
            )
        )
    async_session.add(
        OfficialViolenceCount(
            code_muni=BAURU,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.SP,
            revision=OfficialRevision.PRELIMINAR,
            victim_count=12,
            is_total=False,
            source="SSP-SP",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    assert sp["sp_victims"] == 40
    assert sp["sp_preliminar"] is False

    bauru = next(r for r in coverage if r["code"] == BAURU)
    assert bauru["sp_victims"] == 12
    assert bauru["sp_preliminar"] is True


@pytest.mark.asyncio
async def test_sp_does_not_change_validador_when_only_ssp_exists(
    async_session, setup_sp_ibge
):
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.SP,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=80,
            is_total=False,
            source="SSP-SP",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    assert sp["official_victims"] == 0
    assert sp["official_published"] is False
    assert sp["sp_victims"] == 80
    assert sp["coverage"] is None


@pytest.mark.asyncio
async def test_staging_emits_sp_coverage_keys(async_session, setup_sp_ibge):
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.VALIDADOR,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=10,
            is_total=False,
            source="SINESP VDE",
        )
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.SP,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=80,
            is_total=False,
            source="SSP-SP",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    assert sp["official_victims"] == 10
    for key in SP_COVERAGE_KEYS:
        assert key in sp
    assert sp["sp_victims"] == 80
    assert sp["sp_published"] is True
    assert sp["sp_preliminar"] is False


@pytest.mark.asyncio
async def test_production_omits_sp_coverage_keys(
    async_session, setup_sp_ibge, monkeypatch
):
    """Production JSON omits sp_* keys entirely and never unions SSP-SP (#244 nit)."""
    monkeypatch.setattr(
        "app.services.coverage_data.state_columns_enabled", lambda: False
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.VALIDADOR,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=10,
            is_total=False,
            source="SINESP VDE",
        )
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.SP,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=80,
            is_total=False,
            source="SSP-SP",
        )
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=BAURU,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.SP,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=5,
            is_total=False,
            source="SSP-SP",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    assert sp["official_victims"] == 10
    for key in SP_COVERAGE_KEYS:
        assert key not in sp, f"production payload must omit {key}"

    assert not any(r["code"] == BAURU for r in coverage)
    for row in coverage:
        for key in STATE_COVERAGE_KEYS:
            assert key not in row, f"production payload must omit {key}"


@pytest.mark.asyncio
async def test_rj_mg_sp_coexist_distinct_from_validador(async_session, setup_sp_ibge):
    """Validador / RJ / MG / SP remain four distinct series (#242 #243 #244)."""
    for source_id, code, count in (
        (OfficialSourceId.VALIDADOR, SAO_PAULO, 10),
        (OfficialSourceId.SP, SAO_PAULO, 80),
        (OfficialSourceId.RJ, RIO, 100),
        (OfficialSourceId.MG, BELO_HORIZONTE, 23),
        (OfficialSourceId.VALIDADOR, RIO, 7),
        (OfficialSourceId.VALIDADOR, BELO_HORIZONTE, 4),
    ):
        async_session.add(
            OfficialViolenceCount(
                code_muni=code,
                year_month="2025-09",
                indicator="homicidio_doloso",
                source_id=source_id,
                revision=OfficialRevision.CONSOLIDADO,
                victim_count=count,
                is_total=False,
                source="fixture",
            )
        )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    rio = next(r for r in coverage if r["code"] == RIO)
    bh = next(r for r in coverage if r["code"] == BELO_HORIZONTE)

    assert sp["official_victims"] == 10
    assert sp["sp_victims"] == 80
    assert sp["rj_victims"] == 0
    assert sp["mg_victims"] == 0
    assert sp["official_victims"] != sp["sp_victims"] + sp["rj_victims"] + sp["mg_victims"]

    assert rio["official_victims"] == 7
    assert rio["rj_victims"] == 100
    assert rio["sp_victims"] == 0
    assert rio["mg_victims"] == 0

    assert bh["official_victims"] == 4
    assert bh["mg_victims"] == 23
    assert bh["sp_victims"] == 0
    assert bh["rj_victims"] == 0


@pytest.mark.asyncio
async def test_coverage_download_oficial_ignores_sp(client, async_session, setup_sp_ibge):
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.VALIDADOR,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=10,
            is_total=False,
            source="SINESP VDE",
        )
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.SP,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=80,
            is_total=False,
            source="SSP-SP",
        )
    )
    await async_session.commit()

    response = await client.get("/api/public/stats/coverage/download")
    assert response.status_code == 200
    lines = [line.strip() for line in response.text.strip().splitlines()]
    sp_row = next(line for line in lines[1:] if line.startswith("3550308,"))
    assert sp_row.endswith(",10")
