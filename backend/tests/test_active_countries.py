"""Tests for pipeline_active_countries ingest/classify restriction (issue #217)."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.country_registry import ALL_COUNTRIES
from app.services.classification import ViolentDeathClassification, classify_pending_sources


EXPECTED_ALL = {"AR", "BO", "BR", "CL", "CO", "EC", "GY", "PY", "PE", "SR", "UY", "VE"}

_INGEST_DUMMY = {
    "country": "XX",
    "cities_processed": 0,
    "total_entries": 0,
    "total_sources_created": 0,
    "errors": 0,
    "elapsed_seconds": 0,
    "city_results": {},
}


class _EngineSessionMaker:
    """Create a fresh AsyncSession per async-with block (supports parallel calls)."""

    def __init__(self, engine):
        self._engine = engine

    def __call__(self):
        return _EngineSessionContext(self._engine)


class _EngineSessionContext:
    def __init__(self, engine):
        self._engine = engine
        self._session = None

    async def __aenter__(self):
        self._session = AsyncSession(self._engine)
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        await self._session.close()
        return False


@pytest.fixture
async def classification_batch_db(tmp_path):
    # File-backed SQLite so parallel classify_source sessions share one DB.
    # In-memory + StaticPool races with _reset_unfinished_classifying.
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'active_countries.db'}",
        echo=False,
        future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = _EngineSessionMaker(engine)
    with patch("app.services.classification.async_session_maker", maker):
        yield engine
    await engine.dispose()


def _source(**kwargs):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    defaults = {
        "google_news_id": "test-id",
        "google_news_url": "https://news.example/article",
        "headline": "Test headline",
        "status": SourceStatus.classifying,
    }
    defaults.update(kwargs)
    return SourceGoogleNews(**defaults)


def _classification(**kwargs) -> ViolentDeathClassification:
    defaults = {
        "is_violent_death": True,
        "is_single_incident": True,
        "confidence": "alta",
        "reasoning": "Incident headline",
    }
    defaults.update(kwargs)
    return ViolentDeathClassification(**defaults)


def _called_countries(mock_ingest) -> list[str]:
    return [call.kwargs["country"] for call in mock_ingest.await_args_list]


class TestPipelineActiveCountriesSetting:
    def test_defaults_to_empty_list(self, monkeypatch):
        monkeypatch.delenv("PIPELINE_ACTIVE_COUNTRIES", raising=False)
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.pipeline_active_countries == []

    def test_loads_json_list_from_env(self, monkeypatch):
        monkeypatch.setenv("PIPELINE_ACTIVE_COUNTRIES", '["BR"]')
        from app.config import Settings

        settings = Settings(_env_file=None)
        assert settings.pipeline_active_countries == ["BR"]

    def test_empty_list_means_all_registry_countries(self):
        from app.config import get_pipeline_active_countries

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.pipeline_active_countries = []
            assert set(get_pipeline_active_countries()) == EXPECTED_ALL
            assert len(get_pipeline_active_countries()) == 12

    def test_br_only_returns_just_br(self):
        from app.config import get_pipeline_active_countries

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.pipeline_active_countries = ["BR"]
            assert get_pipeline_active_countries() == ["BR"]


class TestIngestActiveCountries:
    @pytest.mark.asyncio
    async def test_restricted_to_br_does_not_iterate_other_countries(self):
        from app.services.ingestion import ingest_all_countries

        with (
            patch(
                "app.services.ingestion.ingest_all_cities",
                new_callable=AsyncMock,
                return_value=_INGEST_DUMMY,
            ) as mock_ingest,
            patch(
                "app.services.ingestion.get_pipeline_active_countries",
                return_value=["BR"],
            ),
        ):
            result = await ingest_all_countries(when="1h", resolve_urls=False)

        countries = _called_countries(mock_ingest)
        assert countries == ["BR"]
        assert "AR" not in countries
        assert "CL" not in countries
        assert set(result["countries"].keys()) == {"BR"}

    @pytest.mark.asyncio
    async def test_empty_list_still_iterates_all_12(self):
        from app.services.ingestion import ingest_all_countries

        with (
            patch(
                "app.services.ingestion.ingest_all_cities",
                new_callable=AsyncMock,
                return_value=_INGEST_DUMMY,
            ) as mock_ingest,
            patch(
                "app.services.ingestion.get_pipeline_active_countries",
                return_value=list(ALL_COUNTRIES),
            ),
        ):
            result = await ingest_all_countries(when="1h", resolve_urls=False)

        countries = _called_countries(mock_ingest)
        assert set(countries) == EXPECTED_ALL
        assert len(countries) == 12
        assert set(result["countries"].keys()) == EXPECTED_ALL


class TestClassifyActiveCountries:
    @pytest.mark.asyncio
    async def test_restricted_to_br_skips_ar_and_claims_null_as_br(
        self, classification_batch_db
    ):
        from app.models.source_google_news import SourceGoogleNews, SourceStatus

        br_source = _source(
            google_news_id="br-1",
            headline="Homem é morto a tiros no Rio",
            country="BR",
            status=SourceStatus.ready_for_classification,
        )
        ar_source = _source(
            google_news_id="ar-1",
            headline="Homicidio en Buenos Aires deja un muerto",
            country="AR",
            status=SourceStatus.ready_for_classification,
        )
        null_source = _source(
            google_news_id="legacy-br",
            headline="Corpo é encontrado com marcas de violência",
            country=None,
            status=SourceStatus.ready_for_classification,
        )

        async with AsyncSession(classification_batch_db) as session:
            session.add(br_source)
            session.add(ar_source)
            session.add(null_source)
            await session.commit()
            await session.refresh(br_source)
            await session.refresh(ar_source)
            await session.refresh(null_source)
            br_id, ar_id, null_id = br_source.id, ar_source.id, null_source.id

        with (
            patch(
                "app.services.classification.get_pipeline_active_countries",
                return_value=["BR"],
            ),
            patch(
                "app.services.classification.classify_headline",
                return_value=_classification(),
            ) as mock_classify,
        ):
            result = await classify_pending_sources(limit=10, concurrency=3)

        assert result["processed"] == 2
        assert result["violent_death"] == 2
        assert result["discarded"] == 0
        assert "errors" in result
        assert "model_call_errors" not in result
        assert "other_errors" not in result
        assert mock_classify.call_count == 2

        async with AsyncSession(classification_batch_db) as session:
            br_row = await session.get(SourceGoogleNews, br_id)
            ar_row = await session.get(SourceGoogleNews, ar_id)
            null_row = await session.get(SourceGoogleNews, null_id)

        assert br_row.status == SourceStatus.ready_for_download
        assert null_row.status == SourceStatus.ready_for_download
        assert ar_row.status == SourceStatus.ready_for_classification
        assert ar_row.status != SourceStatus.discarded
        assert ar_row.status != SourceStatus.classifying

    @pytest.mark.asyncio
    async def test_unrestricted_still_claims_all_countries(self, classification_batch_db):
        from app.models.source_google_news import SourceGoogleNews, SourceStatus

        br_source = _source(
            google_news_id="all-br",
            headline="Homem é morto a tiros no Rio",
            country="BR",
            status=SourceStatus.ready_for_classification,
        )
        ar_source = _source(
            google_news_id="all-ar",
            headline="Homicidio en Buenos Aires deja un muerto",
            country="AR",
            status=SourceStatus.ready_for_classification,
        )

        async with AsyncSession(classification_batch_db) as session:
            session.add(br_source)
            session.add(ar_source)
            await session.commit()
            await session.refresh(br_source)
            await session.refresh(ar_source)
            br_id, ar_id = br_source.id, ar_source.id

        with (
            patch(
                "app.services.classification.get_pipeline_active_countries",
                return_value=list(ALL_COUNTRIES),
            ),
            patch(
                "app.services.classification.classify_headline",
                return_value=_classification(),
            ),
        ):
            result = await classify_pending_sources(limit=10, concurrency=2)

        assert result["processed"] == 2
        assert "errors" in result
        assert "model_call_errors" not in result

        async with AsyncSession(classification_batch_db) as session:
            br_row = await session.get(SourceGoogleNews, br_id)
            ar_row = await session.get(SourceGoogleNews, ar_id)

        assert br_row.status == SourceStatus.ready_for_download
        assert ar_row.status == SourceStatus.ready_for_download
