"""Tests for Minas Gerais SEJUSP Crimes Violentos adapter (issue #243).

Seam: SEJUSP municipality × month extract → OfficialViolenceCount
(source_id=mg, revision at ingest) → coverage reader keeps Validador
and MG as distinct columns.

Live source (long CSV, semicolon):
https://dados.mg.gov.br/dataset/crimes-violentos
Annual file crimes_violentos_YYYY.csv — columns:
registros;natureza;municipio;cod_municipio;mes;ano;risp;rmbh
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
from app.services.mg_crimes_violentos import (
    MG_CRIMES_VIOLENTOS_PORTAL,
    MG_NATUREZA_TO_VDE,
    build_mg_ibge_lookup,
    ingest_mg_crimes_violentos_rows,
    mg_csv_url,
    parse_mg_crimes_violentos_csv,
)
from app.services.official_typology import map_natureza

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mg_crimes_violentos_2025_slice.csv"

BELO_HORIZONTE = 3106200
CONTAGEM = 3118601
SAO_PAULO = 3550308

MG_IBGE_LOOKUP = build_mg_ibge_lookup([BELO_HORIZONTE, CONTAGEM])


@pytest.fixture
async def setup_mg_ibge(async_session):
    municipalities = [
        IBGEPopulation(
            code_muni=BELO_HORIZONTE,
            name_muni="Belo Horizonte",
            abbrev_state="MG",
            population=2521564,
            year=2022,
        ),
        IBGEPopulation(
            code_muni=CONTAGEM,
            name_muni="Contagem",
            abbrev_state="MG",
            population=673849,
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


def test_portal_and_csv_url():
    assert "dados.mg.gov.br/dataset/crimes-violentos" in MG_CRIMES_VIOLENTOS_PORTAL
    url = mg_csv_url(2025)
    assert url.endswith("crimes_violentos_2025.csv")
    assert "d23fed6e-c59a-488e-a1da-72c5091edb30" in url


def test_mg_natureza_aliases_go_through_shared_map_natureza():
    expected = {
        "HOMICIDIO CONSUMADO (REGISTROS)": ("bag", "homicidio_doloso"),
        "FEMINICIDIO CONSUMADO (REGISTROS)": ("bag", "feminicidio"),
    }
    for mg_label, (kind, indicator) in expected.items():
        vde = MG_NATUREZA_TO_VDE[mg_label]
        mapped = map_natureza(vde)
        assert mapped["kind"] == kind
        assert mapped["indicator"] == indicator


def test_build_mg_ibge_lookup_from_sejusp_prefix():
    lookup = build_mg_ibge_lookup([BELO_HORIZONTE, CONTAGEM, SAO_PAULO])
    assert lookup[310620] == BELO_HORIZONTE
    assert lookup[311860] == CONTAGEM
    assert 355030 not in lookup  # SP excluded


def test_parse_fixture_maps_bag_skips_unmapped_and_window():
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_mg_crimes_violentos_csv(
        text, since="2025-09", ibge_lookup=MG_IBGE_LOOKUP
    )

    assert all(r["year_month"] >= "2025-09" for r in records)
    assert not any(r["year_month"] == "2025-08" for r in records)

    indicators = {r["indicator"] for r in records}
    assert "homicidio_doloso" in indicators
    assert "feminicidio" in indicators
    assert "homicidio_tentado" not in indicators
    assert "estupro" not in indicators

    bh_sep = [
        r for r in records if r["code_muni"] == BELO_HORIZONTE and r["year_month"] == "2025-09"
    ]
    by_ind = {r["indicator"]: r for r in bh_sep}
    assert by_ind["homicidio_doloso"]["victim_count"] == 23
    assert by_ind["homicidio_doloso"]["kind"] == "bag"

    contagem_sep = [
        r for r in records if r["code_muni"] == CONTAGEM and r["year_month"] == "2025-09"
    ]
    assert sum(r["victim_count"] for r in contagem_sep if r["kind"] == "bag") == 6


@pytest.mark.asyncio
async def test_ingest_fixture_writes_source_id_mg(async_session, setup_mg_ibge):
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_mg_crimes_violentos_csv(
        text, since="2025-09", ibge_lookup=MG_IBGE_LOOKUP
    )
    await ingest_mg_crimes_violentos_rows(
        async_session, records, revision=OfficialRevision.CONSOLIDADO
    )

    query = select(OfficialViolenceCount).where(
        OfficialViolenceCount.source_id == OfficialSourceId.MG,
    )
    result = await async_session.execute(query)
    counts = result.scalars().all()

    assert counts
    assert all(c.source_id == OfficialSourceId.MG for c in counts)
    assert all(c.revision == OfficialRevision.CONSOLIDADO for c in counts)
    assert all("SEJUSP" in c.source for c in counts)

    bh_sep_hd = next(
        c
        for c in counts
        if c.code_muni == BELO_HORIZONTE
        and c.year_month == "2025-09"
        and c.indicator == "homicidio_doloso"
    )
    assert bh_sep_hd.victim_count == 23

    bh_oct_hd = next(
        c
        for c in counts
        if c.code_muni == BELO_HORIZONTE
        and c.year_month == "2025-10"
        and c.indicator == "homicidio_doloso"
    )
    assert bh_oct_hd.victim_count == 10

    assert not any(c.year_month == "2025-08" for c in counts)


@pytest.mark.asyncio
async def test_ingest_revision_kwarg(async_session, setup_mg_ibge):
    records = [
        {
            "code_muni": BELO_HORIZONTE,
            "year_month": "2025-09",
            "indicator": "homicidio_doloso",
            "kind": "bag",
            "victim_count": 5,
        }
    ]
    await ingest_mg_crimes_violentos_rows(
        async_session, records, revision=OfficialRevision.PRELIMINAR
    )

    result = await async_session.execute(
        select(OfficialViolenceCount).where(
            OfficialViolenceCount.source_id == OfficialSourceId.MG,
        )
    )
    row = result.scalar_one()
    assert row.revision == OfficialRevision.PRELIMINAR


@pytest.mark.asyncio
async def test_coverage_mg_column_distinct_from_validador(async_session, setup_mg_ibge):
    async_session.add(
        OfficialViolenceCount(
            code_muni=BELO_HORIZONTE,
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
            state="MG",
            city="Belo Horizonte",
            municipality_code=BELO_HORIZONTE,
            event_date=datetime(2025, 9, 15),
            victim_count=4,
            latitude=-19.9167,
            longitude=-43.9345,
        )
    )
    await async_session.commit()

    text = FIXTURE_PATH.read_text(encoding="utf-8")
    records = parse_mg_crimes_violentos_csv(
        text, since="2025-09", ibge_lookup=MG_IBGE_LOOKUP
    )
    await ingest_mg_crimes_violentos_rows(async_session, records)

    coverage = await get_coverage_data(async_session)
    bh = next(r for r in coverage if r["code"] == BELO_HORIZONTE)

    assert bh["official_victims"] == 10
    # Sep 23 + Oct 10 homicidios; Contagem not in this row
    assert bh["mg_victims"] == 33
    assert bh["mg_published"] is True
    assert bh["arquivo_victims"] == 4

    sp = next(r for r in coverage if r["code"] == SAO_PAULO)
    assert sp["official_victims"] == 6
    assert sp["mg_victims"] == 0
    assert sp["mg_published"] is False

    contagem = next(r for r in coverage if r["code"] == CONTAGEM)
    assert contagem["official_victims"] == 0
    assert contagem["mg_victims"] == 6
    assert contagem["mg_published"] is True


@pytest.mark.asyncio
async def test_coverage_mg_prefers_consolidado_over_preliminar(
    async_session, setup_mg_ibge
):
    for revision, count in (
        (OfficialRevision.PRELIMINAR, 50),
        (OfficialRevision.CONSOLIDADO, 40),
    ):
        async_session.add(
            OfficialViolenceCount(
                code_muni=BELO_HORIZONTE,
                year_month="2025-09",
                indicator="homicidio_doloso",
                source_id=OfficialSourceId.MG,
                revision=revision,
                victim_count=count,
                is_total=False,
                source="SEJUSP-MG",
            )
        )
    async_session.add(
        OfficialViolenceCount(
            code_muni=CONTAGEM,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.MG,
            revision=OfficialRevision.PRELIMINAR,
            victim_count=7,
            is_total=False,
            source="SEJUSP-MG",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    bh = next(r for r in coverage if r["code"] == BELO_HORIZONTE)
    assert bh["mg_victims"] == 40
    assert bh["mg_preliminar"] is False

    contagem = next(r for r in coverage if r["code"] == CONTAGEM)
    assert contagem["mg_victims"] == 7
    assert contagem["mg_preliminar"] is True


@pytest.mark.asyncio
async def test_mg_does_not_change_validador_when_only_mg_exists(
    async_session, setup_mg_ibge
):
    async_session.add(
        OfficialViolenceCount(
            code_muni=BELO_HORIZONTE,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.MG,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=23,
            is_total=False,
            source="SEJUSP-MG",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    bh = next(r for r in coverage if r["code"] == BELO_HORIZONTE)
    assert bh["official_victims"] == 0
    assert bh["official_published"] is False
    assert bh["mg_victims"] == 23
    assert bh["coverage"] is None


@pytest.mark.asyncio
async def test_production_does_not_surface_mg_series(
    async_session, setup_mg_ibge, monkeypatch
):
    monkeypatch.setattr(
        "app.services.coverage_data.state_columns_enabled", lambda: False
    )
    async_session.add(
        OfficialViolenceCount(
            code_muni=BELO_HORIZONTE,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.MG,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=23,
            is_total=False,
            source="SEJUSP-MG",
        )
    )
    await async_session.commit()

    coverage = await get_coverage_data(async_session)
    assert not any(r["code"] == BELO_HORIZONTE for r in coverage)


@pytest.mark.asyncio
async def test_coverage_download_oficial_ignores_mg(client, async_session, setup_mg_ibge):
    async_session.add(
        OfficialViolenceCount(
            code_muni=BELO_HORIZONTE,
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
            code_muni=BELO_HORIZONTE,
            year_month="2025-09",
            indicator="homicidio_doloso",
            source_id=OfficialSourceId.MG,
            revision=OfficialRevision.CONSOLIDADO,
            victim_count=23,
            is_total=False,
            source="SEJUSP-MG",
        )
    )
    await async_session.commit()

    response = await client.get("/api/public/stats/coverage/download")
    assert response.status_code == 200
    lines = [line.strip() for line in response.text.strip().splitlines()]
    bh_row = next(line for line in lines[1:] if line.startswith("3106200,"))
    assert bh_row.endswith(",10")
