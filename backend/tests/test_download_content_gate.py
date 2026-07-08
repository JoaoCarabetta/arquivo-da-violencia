"""Tests for post-download content gate wiring (AQV-32)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.classification import ViolentDeathClassification
from app.services.download import DownloadOutcome, download_source_content
from app.services import diagnostics


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def download_db(async_session):
    maker = _TestSessionMaker(async_session)
    with patch("app.services.download.async_session_maker", maker):
        with patch("app.services.diagnostics.async_session_maker", maker):
            yield async_session


def _source(**kwargs):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    defaults = {
        "google_news_id": "download-test",
        "google_news_url": "https://news.example/article",
        "resolved_url": "https://news.example/article",
        "headline": "Homem é morto a tiros em operação policial",
        "status": SourceStatus.ready_for_download,
    }
    defaults.update(kwargs)
    return SourceGoogleNews(**defaults)


def _classification(**kwargs) -> ViolentDeathClassification:
    defaults = {
        "is_violent_death": True,
        "is_single_incident": True,
        "confidence": "alta",
        "reasoning": "Single incident article",
    }
    defaults.update(kwargs)
    return ViolentDeathClassification(**defaults)


@pytest.mark.asyncio
async def test_download_discards_heuristic_aggregate(download_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="heuristic-discard",
        headline="Operação policial deixa mortos",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article</body></html>"
    aggregate_content = (
        "O CVLI registrou 4.241 mortes violentas em 2025 em todo o estado, "
        "segundo balanço anual divulgado pelo governo."
    )

    with patch(
        "app.services.download._fetch_html",
        new=AsyncMock(return_value=(200, html)),
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(aggregate_content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ) as mock_llm, patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ) as mock_record:
        outcome = await download_source_content(source.id)

    assert outcome == DownloadOutcome.discarded
    mock_llm.assert_not_called()
    await download_db.refresh(source)
    assert source.status == SourceStatus.discarded
    assert "content_gate=heuristic" in source.classification_reasoning
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["outcome"] == diagnostics.OUTCOME_DISCARDED


@pytest.mark.asyncio
async def test_download_passes_incident_to_extraction(download_db):
    from app.models.source_google_news import SourceStatus

    source = _source(google_news_id="incident-pass")
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article</body></html>"
    incident_content = (
        "Um homem foi morto a tiros durante operação policial na Zona Norte "
        "do Rio de Janeiro. A polícia civil investiga o caso."
    )

    with patch(
        "app.services.download._fetch_html",
        new=AsyncMock(return_value=(200, html)),
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(incident_content, None),
    ), patch(
        "app.services.download.classify_article_content",
        return_value=_classification(),
    ):
        outcome = await download_source_content(source.id)

    assert outcome == DownloadOutcome.ready_for_extraction
    await download_db.refresh(source)
    assert source.status == SourceStatus.ready_for_extraction
    assert incident_content in source.content


@pytest.mark.asyncio
async def test_download_discards_llm_rejection(download_db):
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="llm-discard",
        headline="Tiroteio deixa mortos",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article</body></html>"
    ambiguous_content = (
        "Autoridades divulgaram dados sobre violência urbana em várias regiões "
        "do país durante coletiva nesta terça-feira."
    )

    with patch(
        "app.services.download._fetch_html",
        new=AsyncMock(return_value=(200, html)),
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(ambiguous_content, None),
    ), patch(
        "app.services.download.classify_article_content",
        return_value=_classification(
            is_single_incident=False,
            content_class_hint="aggregate_statistics",
            reasoning="Article is a statistics roundup",
        ),
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ) as mock_record:
        outcome = await download_source_content(source.id)

    assert outcome == DownloadOutcome.discarded
    await download_db.refresh(source)
    assert source.status == SourceStatus.discarded
    assert "content_gate=llm" in source.classification_reasoning
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["outcome"] == diagnostics.OUTCOME_DISCARDED
    assert mock_record.call_args.kwargs["failure_reason"] == diagnostics.LLM_CONTENT_REJECT
