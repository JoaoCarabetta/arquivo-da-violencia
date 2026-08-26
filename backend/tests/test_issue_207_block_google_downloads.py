"""Test issue #207: Block downloads from Google News URLs when unwrap fails.

When unwrap cannot produce a newspaper URL (both at ingest and at download),
the source must not be fetched from the Google News URL. It stays failed or waiting.
Extract never runs on a Google page. Late unwrap still allowed if it succeeds.

Fixtures only - no live Google calls.
"""

from unittest.mock import AsyncMock, patch, call

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.services.download import download_classified_sources, download_source_content


class _TestSessionMaker:
    """Test session maker for mocking."""
    
    def __init__(self, session):
        self._session = session
    
    def __call__(self):
        return self
    
    async def __aenter__(self):
        return self._session
    
    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
async def test_db():
    """Create an in-memory test database."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    async with AsyncSession(engine) as session:
        yield session
    
    await engine.dispose()


@pytest.mark.asyncio
async def test_no_download_from_google_when_unwrap_fails(test_db):
    """
    Acceptance 1: A source with empty newspaper URL and only a Google News URL
    is not downloaded from news.google.com.
    
    When a source has:
    - status = ready_for_download
    - resolved_url = NULL (initial unwrap failed)
    - google_news_url = a news.google.com URL
    
    And late unwrap also fails (returns None), the source should:
    - NOT fetch HTTP from the Google News URL
    - Be marked as failed (not extracted)
    - NOT reach status ready_for_extraction
    """
    source = SourceGoogleNews(
        google_news_id="test-unwrap-fails",
        google_news_url="https://news.google.com/articles/CBMabcdef",
        resolved_url=None,  # Initial unwrap failed
        headline="Homem é morto em tiroteio",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    maker = _TestSessionMaker(test_db)
    
    mock_fetch = AsyncMock()
    
    with (
        patch("app.services.download.async_session_maker", maker),
        patch("app.services.diagnostics.async_session_maker", maker),
        # Late unwrap also fails
        patch("app.services.ingestion.resolve_google_news_url", return_value=None),
        # HTTP fetch should NOT be called
        patch("app.services.download._fetch_html", new=mock_fetch),
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # Should process but not succeed
    assert result["processed"] == 1, f"Expected 1 processed, got {result['processed']}"
    assert result["successful"] == 0, f"Expected 0 successful, got {result['successful']}"
    assert result["failed"] == 1, f"Expected 1 failed, got {result['failed']}"
    
    # HTTP fetch should NOT have been called with the Google News URL
    mock_fetch.assert_not_called()
    
    # Source should be marked failed, not ready_for_extraction
    await test_db.refresh(source)
    assert source.status == SourceStatus.failed_in_download, (
        f"Expected status failed_in_download, got {source.status}"
    )
    assert source.content is None, "Content should not be set when download blocked"


@pytest.mark.asyncio
async def test_late_unwrap_success_downloads_from_newspaper(test_db):
    """
    Acceptance 2: Late unwrap still runs once; success persists the newspaper URL
    and download proceeds as today.
    
    When a source has:
    - status = ready_for_download
    - resolved_url = NULL (initial unwrap failed)
    - google_news_url present
    
    And late unwrap succeeds, the source should:
    - Have the newspaper URL persisted to resolved_url
    - Download from the newspaper URL (NOT Google)
    - Reach ready_for_extraction status
    """
    source = SourceGoogleNews(
        google_news_id="test-late-unwrap-success",
        google_news_url="https://news.google.com/articles/CBMxyz789",
        resolved_url=None,  # Initial unwrap failed
        headline="Tiroteio deixa dois mortos",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    maker = _TestSessionMaker(test_db)
    newspaper_url = "https://g1.globo.com/rj/rio-de-janeiro/noticia/2024/tiroteio.html"
    html = "<html><body>Tiroteio deixa dois mortos na Zona Norte.</body></html>"
    content = "Tiroteio deixa dois mortos na Zona Norte."
    
    mock_fetch = AsyncMock(return_value=(200, html))
    
    with (
        patch("app.services.download.async_session_maker", maker),
        patch("app.services.diagnostics.async_session_maker", maker),
        # Late unwrap succeeds
        patch("app.services.ingestion.resolve_google_news_url", return_value=newspaper_url),
        # HTTP fetch called with newspaper URL
        patch("app.services.download._fetch_html", new=mock_fetch),
        patch("app.services.download.extract_content_and_metadata", return_value=(content, None)),
        patch("app.services.download.classify_article_content", new=AsyncMock()),
        patch("app.services.download.passes_content_gate", return_value=True),
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # Should succeed
    assert result["processed"] == 1
    assert result["successful"] == 1
    assert result["failed"] == 0
    
    # HTTP fetch should be called with the newspaper URL, NOT the Google URL
    mock_fetch.assert_called_once()
    called_url = mock_fetch.call_args[0][0]
    assert called_url == newspaper_url, (
        f"Expected fetch to be called with newspaper URL {newspaper_url}, "
        f"but was called with {called_url}"
    )
    assert "news.google.com" not in called_url, "Should not fetch from Google News URL"
    
    # Newspaper URL should be persisted
    await test_db.refresh(source)
    assert source.resolved_url == newspaper_url, (
        f"Expected resolved_url to be persisted as {newspaper_url}, "
        f"got {source.resolved_url}"
    )
    assert source.status == SourceStatus.ready_for_extraction
    assert source.content == content


@pytest.mark.asyncio
async def test_existing_newspaper_url_unchanged(test_db):
    """
    Acceptance 3: Existing rows that already have a newspaper URL are unchanged.
    
    This is a regression test. Sources that have resolved_url already set
    should continue to work normally (Chile/Brazil).
    """
    newspaper_url = "https://g1.globo.com/rj/rio-de-janeiro/noticia/2024/article.html"
    source = SourceGoogleNews(
        google_news_id="test-existing-url",
        google_news_url="https://news.google.com/articles/CBMabc123",
        resolved_url=newspaper_url,  # Already has newspaper URL
        headline="Operação policial termina em confronto",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    maker = _TestSessionMaker(test_db)
    html = "<html><body>Operação policial termina em confronto.</body></html>"
    content = "Operação policial termina em confronto."
    
    mock_fetch = AsyncMock(return_value=(200, html))
    mock_resolve = AsyncMock()
    
    with (
        patch("app.services.download.async_session_maker", maker),
        patch("app.services.diagnostics.async_session_maker", maker),
        # Late unwrap should NOT be called (already have resolved_url)
        patch("app.services.ingestion.resolve_google_news_url", new=mock_resolve),
        patch("app.services.download._fetch_html", new=mock_fetch),
        patch("app.services.download.extract_content_and_metadata", return_value=(content, None)),
        patch("app.services.download.classify_article_content", new=AsyncMock()),
        patch("app.services.download.passes_content_gate", return_value=True),
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # Should succeed normally
    assert result["processed"] == 1
    assert result["successful"] == 1
    assert result["failed"] == 0
    
    # Late unwrap should NOT be called (already have URL)
    mock_resolve.assert_not_called()
    
    # Should fetch from the existing newspaper URL
    mock_fetch.assert_called_once()
    called_url = mock_fetch.call_args[0][0]
    assert called_url == newspaper_url, (
        f"Expected fetch with existing newspaper URL {newspaper_url}, "
        f"got {called_url}"
    )
    
    # URL should remain unchanged
    await test_db.refresh(source)
    assert source.resolved_url == newspaper_url
    assert source.status == SourceStatus.ready_for_extraction


@pytest.mark.asyncio
async def test_no_urls_marks_failed(test_db):
    """
    Edge case: Source with no resolved_url AND no google_news_url
    should be marked failed immediately.
    """
    source = SourceGoogleNews(
        google_news_id="test-no-urls",
        google_news_url="",  # Empty Google URL (NOT NULL constraint)
        resolved_url=None,  # No newspaper URL
        headline="Test article",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    maker = _TestSessionMaker(test_db)
    mock_fetch = AsyncMock()
    
    with (
        patch("app.services.download.async_session_maker", maker),
        patch("app.services.diagnostics.async_session_maker", maker),
        patch("app.services.download._fetch_html", new=mock_fetch),
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # Should be marked failed
    assert result["processed"] == 1
    assert result["failed"] == 1
    
    # No HTTP fetch
    mock_fetch.assert_not_called()
    
    # Should be failed
    await test_db.refresh(source)
    assert source.status == SourceStatus.failed_in_download
