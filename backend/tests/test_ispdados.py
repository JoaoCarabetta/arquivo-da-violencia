"""Tests for Rio de Janeiro ISPDados adapter (issue #242).

Seam: ISPDados municipality × month extract → OfficialViolenceCount
(source_id=rj, revision from `fase`) → coverage reader keeps Validador
and RJ as distinct columns.

Live source (wide CSV, semicolon, latin-1):
https://www.ispdados.rj.gov.br/Arquivos/BaseMunicipioMensal.csv
Portal: https://www.ispdados.rj.gov.br/estatistica.html
`fase`: 1 = parcial/preliminar, 2 = consolidado, 3 = consolidado com errata.
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
from app.services.ispdados import (
    ISP_COLUMN_TO_NATUREZA,
    ISPDADOS_CSV_URL,
    ingest_ispdados_rows,
    parse_ispdados_csv,
    revision_from_fase,
)
from app.services.official_typology import map_natureza

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ispdados_municipio_mensal.csv"

RIO = 3304557
NITEROI = 3303302
SAO_GONCALO = 3304904
SAO_PAULO = 3550308


@pytest.fixture
async def setup_rj_ibge(async_session):
    municipalities = [
        IBGEPopulation(
            code_muni=RIO,
            name_muni="Rio de Janeiro",
            abbrev_state="RJ",
            population=6775561,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=NITEROI,
            name_muni="Niterói",
            abbrev_state="RJ",
            population=515317,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=SAO_GONCALO,
            name_muni="São Gonçalo",
            abbrev_state="RJ",
            population=896744,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=SAO_PAULO,
            name_muni="São Paulo",
            abbrev_state="SP",
            population=12396372,
            year=2022,
        ),
    ]
    for muni in municipalities:
        async_session.add(muni)
    await async_session.commit()


def test_source_url_points_at_ispdados_municipal_monthly():
    assert ISPDADOS_CSV_URL.endswith("BaseMunicipioMensal.csv")
    assert "ispdados.rj.gov.br" in ISPDADOS_CSV_URL


@pytest.mark.parametrize(
    "fase,expected",
    [
        ("1", OfficialRevision.PRELIMINAR),
        (1, OfficialRevision.PRELIMINAR),
        ("2", OfficialRevision.CONSOLIDADO),
        ("3", OfficialRevision.CONSOLIDADO),
        (3, OfficialRevision.CONSOLIDADO),
    ],
)
def test_revision_from_fase(fase, expected):
    assert revision_from_fase(fase) == expected


def test_isp_column_aliases_go_through_shared_map_natureza():
    """Thin RJ normalizer only; typology stays in map_natureza (#239)."""
    expected = {
        "hom_doloso": ("bag", "homicidio_doloso"),
        "feminicidio": ("bag", "feminicidio"),
        "latrocinio": ("bag", "latrocinio"),
        "lesao_corp_morte": ("bag", "lesao_corporal_seguida_morte"),
        "hom_por_interv_policial": ("extra", "morte_intervencao_policial"),
    }
    for column, (kind, indicator) in expected.items():
        natureza = ISP_COLUMN_TO_NATUREZA[column]
        mapped = map_natureza(natureza)
        assert mapped["kind"] == kind
        assert mapped["indicator"] == indicator


def test_parse_fixture_unpivots_mapped_skips_composites_and_window():
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_ispdados_csv(text, since="2025-09")

    # Window: August 2025 dropped
    assert all(r["year_month"] >= "2025-09" for r in records)
    assert not any(r["year_month"] == "2025-08" for r in records)

    # Composites / unmapped columns never become store rows
    stored_indicators = {r["indicator"] for r in records}
    assert "cvli" not in stored_indicators
    assert "letalidade_violenta" not in stored_indicators
    assert "tentat_hom" not in stored_indicators
    assert "tentativa_feminicidio" not in stored_indicators

    rio_sep = [
        r for r in records if r["code_muni"] == RIO and r["year_month"] == "2025-09"
    ]
    by_ind = {r["indicator"]: r for r in rio_sep}
    assert by_ind["homicidio_doloso"]["victim_count"] == 100
    assert by_ind["lesao_corporal_seguida_morte"]["victim_count"] == 1
    assert by_ind["latrocinio"]["victim_count"] == 4
    assert by_ind["feminicidio"]["victim_count"] == 4
    assert by_ind["morte_intervencao_policial"]["victim_count"] == 27
    assert by_ind["homicidio_doloso"]["revision"] == OfficialRevision.CONSOLIDADO
    assert by_ind["homicidio_doloso"]["kind"] == "bag"
    assert by_ind["morte_intervencao_policial"]["kind"] == "extra"

    rio_oct = [
        r
        for r in records
        if r["code_muni"] == RIO and r["year_month"] == "2025-10"
    ]
    assert rio_oct
    assert all(r["revision"] == OfficialRevision.PRELIMINAR for r in rio_oct)


@pytest.mark.asyncio
async def test_ingest_fixture_writes_source_id_rj(async_session, setup_rj_ibge):
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_ispdados_csv(text, since="2025-09")
    await ingest_ispdados_rows(async_session, records)

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.source_id == OfficialSourceId.RJ,
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert counts
    assert all(c.source_id == OfficialSourceId.RJ for c in counts)
    assert all(c.source.startswith("ISPDados") for c in counts)

    rio_sep_hd = next(
        c
        for c in counts
        if c.code_muni == RIO
        and c.year_month == "2025-09"
        and c.indicator == "homicidio_doloso"
    )
    assert rio_sep_hd.victim_count == 100
    assert rio_sep_hd.revision == OfficialRevision.CONSOLIDADO

    rio_oct_hd = next(
        c
        for c in counts
        if c.code_muni == RIO
        and c.year_month == "2025-10"
        and c.indicator == "homicidio_doloso"
    )
    assert rio_oct_hd.victim_count == 20
    assert rio_oct_hd.revision == OfficialRevision.PRELIMINAR

    # Unmapped / composites absent
    assert not any(c.indicator in {"cvli", "letalidade_violenta", "tentat_hom"} for c in counts)

    # Pre-window August not stored
    assert not any(c.year_month == "2025-08" for c in counts)


@pytest.mark.asyncio
async def test_ingest_unmapped_natureza_not_stored(async_session, setup_rj_ibge):
    records = [
        {
            "code_muni": RIO,
            "year_month": "2025-09",
            "natureza": "Suicídio",
            "indicator": None,
            "kind": "unmapped",
            "victim_count": 9,
            "revision": OfficialRevision.CONSOLIDADO,
        }
    ]
    await ingest_ispdados_rows(async_session, records)

    result = await async_session.execute(select(OfficialViolenceCount))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_coverage_rj_column_distinct_from_validador(async_session, setup_rj_ibge):
    """RJ bag is its own series; never summed into official_victims (#242 / #237)."""
    # Validador consolidado for Rio: 10
    async_session.add(
        OfficialViolenceCount(
            code_muni=RIO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.VALIDADOR,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=10,
            is_total=False,
            source="SINESP VDE",
        )
    )
    # Validador for São Paulo so we can assert SP has no RJ series
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_PAULO,
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
            state="RJ",
            city="Rio de Janeiro",
            municipality_code=RIO,
            event_date=datetime(2025, 9, 15),
            victim_count=3,
            latitude=-22.9068,
            longitude=-43.1729,
        )
    )
    await async_session.commit()

    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_ispdados_csv(text, since="2025-09")
    await ingest_ispdados_rows(async_session, records)

    coverage = await get_coverage_data(async_session)
    rio = next(r for r in coverage if r["code"] == RIO)

    # Validador primary total unchanged (10, not 10+ISP bag)
    assert rio["official_victims"] == 10
    # ISP bag for Rio: Sep consolidado 100+1+4+4=109 plus Oct preliminar 20+0+1+0=21 → 130
    # Extra (intervenção) excluded from both bag totals
    assert rio["rj_victims"] == 130
    assert rio["rj_published"] is True
    assert rio["arquivo_victims"] == 3

    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    assert sp["official_victims"] == 6
    assert sp["rj_victims"] == 0
    assert sp["rj_published"] is False

    # Niterói appears from RJ column even without Validador / Arquivo
    niteroi = next(r for r in coverage if r["code"] == NITEROI)
    assert niteroi["official_victims"] == 0
    assert niteroi["rj_victims"] == 9  # 8 HD + 1 feminicidio
    assert niteroi["rj_published"] is True


@pytest.mark.asyncio
async def test_coverage_rj_prefers_consolidado_over_preliminar(
    async_session, setup_rj_ibge
):
    """Same municipality × month: consolidado wins; preliminar-only is flagged."""
    for revision, count in (
        (OfficialRevision.PRELIMINAR, 50),
        (OfficialRevision.CONSOLIDADO, 40),
    ):
        async_session.add(
            OfficialViolenceCount(
                code_muni=RIO,
                year_month="2025-09",
                indicator="homicidio_doloso",
                source_id=OfficialSourceId.RJ,
                revision=revision,
                victim_count=count,
                is_total=False,
                source="ISPDados",
            )
        )
    # São Gonçalo: preliminar only
    async_session.add(
        OfficialViolenceCount(
            code_muni=SAO_GONCALO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.RJ,
            revision=OfficialRevision.PRELIMINAR,
            victim_count=12,
            is_total=False,
            source="ISPDados",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    rio = next(r for r in coverage if r["code"] == RIO)
    assert rio["rj_victims"] == 40
    assert rio["rj_preliminar"] is False

    sg = next(r for r in coverage if r["code"] == SAO_GONCALO)
    assert sg["rj_victims"] == 12
    assert sg["rj_preliminar"] is True


@pytest.mark.asyncio
async def test_rj_does_not_change_validador_when_only_isp_exists(
    async_session, setup_rj_ibge
):
    async_session.add(
        OfficialViolenceCount(
            code_muni=RIO,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.RJ,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=100,
            is_total=False,
            source="ISPDados",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    rio = next(r for r in coverage if r["code"] == RIO)
    assert rio["official_victims"] == 0
    assert rio["official_published"] is False
    assert rio["rj_victims"] == 100
    assert rio["coverage"] is None


RJ_COVERAGE_KEYS = ("rj_victims", "rj_published", "rj_preliminar")


@pytest.mark.asyncio
async def test_staging_emits_rj_coverage_keys(async_session, setup_rj_ibge):
    """Staging/dev coverage rows include the distinct RJ series keys (#242 nit)."""
    async_session.add(
        OfficialViolenceCount(
            code_muni=RIO,
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
            source_id=OfficialSourceId.RJ,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=100,
            is_total=False,
            source="ISPDados",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    rio = next(r for r in coverage if r["code"] == RIO)
    assert rio["official_victims"] == 10
    for key in RJ_COVERAGE_KEYS:
        assert key in rio
    assert rio["rj_victims"] == 100
    assert rio["rj_published"] is True
    assert rio["rj_preliminar"] is False


@pytest.mark.asyncio
async def test_production_omits_rj_coverage_keys(
    async_session, setup_rj_ibge, monkeypatch
):
    """Production JSON omits rj_* keys entirely and never unions ISPDados (#242 nit)."""
    monkeypatch.setattr(
        "app.services.coverage_data.state_columns_enabled", lambda: False
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=RIO,
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
            source_id=OfficialSourceId.RJ,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=100,
            is_total=False,
            source="ISPDados",
        )
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=NITEROI,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.RJ,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=8,
            is_total=False,
            source="ISPDados",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    rio = next(r for r in coverage if r["code"] == RIO)
    assert rio["official_victims"] == 10
    for key in RJ_COVERAGE_KEYS:
        assert key not in rio, f"production payload must omit {key}"

    assert not any(r["code"] == NITEROI for r in coverage)
    for row in coverage:
        for key in RJ_COVERAGE_KEYS:
            assert key not in row


@pytest.mark.asyncio
async def test_coverage_download_oficial_ignores_rj(client, async_session, setup_rj_ibge):
    """Download CSV `oficial` stays Validador-only so RJ cannot pollute it."""
    async_session.add(
        OfficialViolenceCount(
            code_muni=RIO,
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
            source_id=OfficialSourceId.RJ,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=100,
            is_total=False,
            source="ISPDados",
        )
    )
    await async_session.commit()

    response = await client.get("/api/public/stats/coverage/download")
    assert response.status_code == 200
    lines = [line.strip() for line in response.text.strip().splitlines()]
    rio_row = next(line for line in lines[1:] if line.startswith("3304557,"))
    # code,name,uf,oficial — Validador 10, not 10+100
    assert rio_row.endswith(",10")


def test_decode_latin1_ispdados_bytes():
    from app.services.ispdados import decode_ispdados_bytes

    raw = "fmun;fmun_cod\nAperibé;3300100\n".encode("latin-1")
    text = decode_ispdados_bytes(raw)
    assert "Aperibé" in text
