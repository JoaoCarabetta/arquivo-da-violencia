"""Tests for headline classification filters (AQV-31)."""

from unittest.mock import patch

import pytest

from app.services.classification import (
    ViolentDeathClassification,
    classify_source,
)


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
async def test_classify_source_passes_single_incident(async_session):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    source = SourceGoogleNews(
        headline="Homem é morto a tiros em operação policial no Rio",
        status=SourceStatus.classifying,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

    with patch(
        "app.services.classification.classify_headline",
        return_value=_classification(),
    ):
        result = await classify_source(source.id)

    assert result is True
    await async_session.refresh(source)
    assert source.status == SourceStatus.ready_for_download


@pytest.mark.asyncio
async def test_classify_source_discards_aggregate_headline(async_session):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    source = SourceGoogleNews(
        headline="CVLI: estado registra 4.241 mortes violentas em 2025",
        status=SourceStatus.classifying,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

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
    await async_session.refresh(source)
    assert source.status == SourceStatus.discarded
    assert "single_incident=false" in source.classification_reasoning


@pytest.mark.asyncio
async def test_classify_source_discards_foreign_disaster(async_session):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    source = SourceGoogleNews(
        headline="Terremoto na Venezuela deixa centenas de mortos",
        status=SourceStatus.classifying,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

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
    await async_session.refresh(source)
    assert source.status == SourceStatus.discarded


@pytest.mark.asyncio
async def test_classify_source_discards_non_violent_death(async_session):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    source = SourceGoogleNews(
        headline="Polícia prende suspeito de roubo",
        status=SourceStatus.classifying,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

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
    await async_session.refresh(source)
    assert source.status == SourceStatus.discarded
