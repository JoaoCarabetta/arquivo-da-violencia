"""Tests for headline classification filters (AQV-31)."""

from unittest.mock import patch

import pytest

from app.services.classification import (
    ViolentDeathClassification,
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


def test_schema_requires_single_incident_field():
    result = ViolentDeathClassification(
        is_violent_death=True,
        is_single_incident=False,
        confidence="alta",
        reasoning="Aggregate stats headline",
        content_class_hint="aggregate_statistics",
    )
    assert result.is_single_incident is False
    assert result.content_class_hint == "aggregate_statistics"


@pytest.mark.asyncio
async def test_classify_source_passes_single_incident(classification_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="pass-1",
        headline="Homem é morto a tiros em operação policial no Rio",
    )
    classification_db.add(source)
    await classification_db.commit()
    await classification_db.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        return_value=_classification(),
    ):
        result = await classify_source(source.id)

    assert result is True
    await classification_db.refresh(source)
    assert source.status == SourceStatus.ready_for_download


@pytest.mark.asyncio
async def test_classify_source_discards_aggregate_headline(classification_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="aggregate-1",
        headline="CVLI: estado registra 4.241 mortes violentas em 2025",
    )
    classification_db.add(source)
    await classification_db.commit()
    await classification_db.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        return_value=_classification(
            is_single_incident=False,
            content_class_hint="aggregate_statistics",
            reasoning="Year-end statistics, not a single incident",
        ),
    ):
        result = await classify_source(source.id)

    assert result is False
    await classification_db.refresh(source)
    assert source.status == SourceStatus.discarded
    assert "single_incident=false" in source.classification_reasoning


@pytest.mark.asyncio
async def test_classify_source_discards_foreign_disaster(classification_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="foreign-1",
        headline="Terremoto na Venezuela deixa centenas de mortos",
    )
    classification_db.add(source)
    await classification_db.commit()
    await classification_db.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        return_value=_classification(
            is_violent_death=True,
            is_single_incident=False,
            content_class_hint="foreign",
            reasoning="Foreign disaster report",
        ),
    ):
        result = await classify_source(source.id)

    assert result is False
    await classification_db.refresh(source)
    assert source.status == SourceStatus.discarded


@pytest.mark.asyncio
async def test_classify_source_discards_non_violent_death(classification_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="non-violent-1",
        headline="Polícia prende suspeito de roubo",
    )
    classification_db.add(source)
    await classification_db.commit()
    await classification_db.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        return_value=_classification(
            is_violent_death=False,
            is_single_incident=False,
            reasoning="No death mentioned",
        ),
    ):
        result = await classify_source(source.id)

    assert result is False
    await classification_db.refresh(source)
    assert source.status == SourceStatus.discarded
