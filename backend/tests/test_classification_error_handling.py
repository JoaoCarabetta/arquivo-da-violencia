"""Tests for classification error handling vs content-gate discards (issue #215)."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.classification import (
    ClassificationModelCallError,
    ViolentDeathClassification,
    classify_pending_sources,
    classify_source,
)


class _TestSessionMaker:
    """Route classification DB calls through the pytest async_session."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def classification_db(async_session):
    maker = _TestSessionMaker(async_session)
    with patch("app.services.classification.async_session_maker", maker):
        yield async_session


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
def classification_batch_db(async_engine):
    maker = _EngineSessionMaker(async_engine)
    with patch("app.services.classification.async_session_maker", maker):
        yield async_engine


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


class InsufficientCreditsError(Exception):
    """Simulates OpenRouter HTTP 402 insufficient credits."""

    def __init__(self):
        super().__init__("402 Insufficient credits")


@pytest.mark.asyncio
async def test_classify_source_raises_on_model_call_failure(classification_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="model-fail-1",
        headline="Homem é morto a tiros em operação policial",
    )
    classification_db.add(source)
    await classification_db.commit()
    await classification_db.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        side_effect=InsufficientCreditsError(),
    ):
        with pytest.raises(ClassificationModelCallError) as exc_info:
            await classify_source(source.id)

    assert "402" in str(exc_info.value) or "Insufficient credits" in str(
        exc_info.value
    )
    await classification_db.refresh(source)
    assert source.status == SourceStatus.ready_for_classification


@pytest.mark.asyncio
async def test_classify_pending_sources_counts_model_errors_not_discards(
    classification_batch_db,
):
    from app.models.source_google_news import SourceStatus

    batch_size = 4
    sources = []
    async with AsyncSession(classification_batch_db) as session:
        for i in range(batch_size):
            source = _source(
                google_news_id=f"batch-fail-{i}",
                headline=f"Headline {i} about violent death",
                status=SourceStatus.ready_for_classification,
            )
            session.add(source)
            sources.append(source)
        await session.commit()
        for source in sources:
            await session.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        side_effect=InsufficientCreditsError(),
    ):
        result = await classify_pending_sources(limit=batch_size, concurrency=2)

    assert result["processed"] == batch_size
    assert result["violent_death"] == 0
    assert result["discarded"] == 0
    assert result["errors"] == batch_size
    assert result["model_call_errors"] == batch_size
    assert result["other_errors"] == 0

    for source in sources:
        async with AsyncSession(classification_batch_db) as session:
            row = await session.get(type(source), source.id)
        assert row.status == SourceStatus.ready_for_classification


@pytest.mark.asyncio
async def test_classify_pending_sources_mixed_discard_and_model_errors(
    classification_batch_db,
):
    from app.models.source_google_news import SourceStatus

    discard_source = _source(
        google_news_id="discard-1",
        headline="Polícia prende suspeito de roubo",
        status=SourceStatus.ready_for_classification,
    )
    fail_sources = [
        _source(
            google_news_id=f"fail-{i}",
            headline=f"Fail headline {i}",
            status=SourceStatus.ready_for_classification,
        )
        for i in range(3)
    ]
    async with AsyncSession(classification_batch_db) as session:
        session.add(discard_source)
        for source in fail_sources:
            session.add(source)
        await session.commit()
        await session.refresh(discard_source)
        for source in fail_sources:
            await session.refresh(source)

    discard_headline = discard_source.headline

    def classify_side_effect(headline: str, **_kwargs):
        if headline == discard_headline:
            return _classification(
                is_violent_death=False,
                is_single_incident=False,
                reasoning="No death mentioned",
            )
        raise InsufficientCreditsError()

    with patch(
        "app.services.classification.classify_headline",
        side_effect=classify_side_effect,
    ):
        result = await classify_pending_sources(limit=10, concurrency=3)

    assert result["processed"] == 4
    assert result["violent_death"] == 0
    assert result["discarded"] == 1
    assert result["errors"] == 3
    assert result["model_call_errors"] == 3
    assert result["other_errors"] == 0

    from app.models.source_google_news import SourceGoogleNews

    async with AsyncSession(classification_batch_db) as session:
        row = await session.get(SourceGoogleNews, discard_source.id)
    assert row.status == SourceStatus.discarded
    for source in fail_sources:
        async with AsyncSession(classification_batch_db) as session:
            row = await session.get(SourceGoogleNews, source.id)
        assert row.status == SourceStatus.ready_for_classification


@pytest.mark.asyncio
async def test_classify_task_requeues_on_model_call_error(classification_db):
    from app.models.source_google_news import SourceStatus
    from app.tasks.pipeline import classify_task

    source = _source(
        google_news_id="task-fail-1",
        headline="Homem é morto a tiros em operação policial",
    )
    classification_db.add(source)
    await classification_db.commit()
    await classification_db.refresh(source)
    source_id = source.id

    ctx = {"redis": AsyncMock()}

    with patch(
        "app.services.classification.classify_headline",
        side_effect=InsufficientCreditsError(),
    ):
        result = await classify_task(ctx, source_id)

    assert result["status"] != "completed"
    assert result["status"] == "requeued"
    assert "is_violent_death" not in result
    assert result["reason"] == "model_call_error"
    assert result["task"] == "classify"
    assert result["source_id"] == source_id

    await classification_db.refresh(source)
    assert source.status == SourceStatus.ready_for_classification
