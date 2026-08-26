"""Test download behavior when resolved_url is NULL.

Issue #171: download_classified_sources skips ready_for_download rows
that have resolved_url=NULL but google_news_url present.

Root cause: resolve_google_news_url can return None (decoder failure),
ingest still inserts the source, classify marks ready_for_download,
but download filters WHERE resolved_url IS NOT NULL.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.services.download import download_classified_sources


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
async def test_download_processes_null_resolved_url_with_late_resolution_success(test_db):
    """
    Test that sources with NULL resolved_url are processed when late resolution succeeds.
    
    When a source has:
    - status = ready_for_download
    - resolved_url = NULL (initial decoder failure)
    - google_news_url present
    
    And late resolution succeeds, the source should be:
    - Processed (processed==1)
    - resolved_url persisted to database
    - Downloaded from the resolved URL
    """
    source = SourceGoogleNews(
        google_news_id="test-null-resolved-success",
        google_news_url="https://news.google.com/articles/test123",
        resolved_url=None,  # Initial decoder failure
        headline="Homem é morto a tiros em operação policial",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    maker = _TestSessionMaker(test_db)
    html = "<html><body>Homem foi morto durante operação policial.</body></html>"
    content = "Homem foi morto durante operação policial."
    resolved_url_result = "https://example.com/article-resolved"
    
    with (
        patch("app.services.download.async_session_maker", maker),
        patch("app.services.diagnostics.async_session_maker", maker),
        patch("app.services.ingestion.resolve_google_news_url", return_value=resolved_url_result) as mock_resolve,
        patch("app.services.download._fetch_html", new=AsyncMock(return_value=(200, html))),
        patch("app.services.download.extract_content_and_metadata", return_value=(content, None)),
        patch("app.services.download.classify_article_content", new=AsyncMock()),
        patch("app.services.download.passes_content_gate", return_value=True),
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # Should process 1 source
    assert result["processed"] == 1, f"Expected 1 processed, got {result['processed']}"
    assert result["successful"] == 1, f"Expected 1 successful, got {result['successful']}"
    
    # Verify resolved_url was persisted
    await test_db.refresh(source)
    assert source.resolved_url == resolved_url_result, (
        f"Expected resolved_url to be persisted as {resolved_url_result}, "
        f"but got {source.resolved_url}"
    )


@pytest.mark.asyncio
async def test_download_processes_null_resolved_url_with_late_resolution_failure(test_db):
    """
    Test that sources with NULL resolved_url are NOT downloaded when late resolution fails.
    
    Issue #207: When unwrap fails both at ingest and at download time, do NOT fetch
    from the Google News URL. Mark the source as failed instead.
    
    When a source has:
    - status = ready_for_download
    - resolved_url = NULL (initial decoder failure)
    - google_news_url present
    
    And late resolution ALSO fails (returns None), the source should:
    - Be processed but marked FAILED (not downloaded from Google News URL)
    - NOT reach ready_for_extraction status
    """
    source = SourceGoogleNews(
        google_news_id="test-null-resolved-failure",
        google_news_url="https://news.google.com/articles/test456",
        resolved_url=None,  # Initial decoder failure
        headline="Tiroteio deixa dois mortos na Zona Norte",
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
        patch("app.services.ingestion.resolve_google_news_url", return_value=None),  # Late resolution also fails
        patch("app.services.download._fetch_html", new=mock_fetch),  # Should NOT be called
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # Should be processed but failed (NOT downloaded from Google News URL)
    assert result["processed"] == 1, f"Expected 1 processed, got {result['processed']}"
    assert result["successful"] == 0, f"Expected 0 successful, got {result['successful']}"
    assert result["failed"] == 1, f"Expected 1 failed, got {result['failed']}"
    
    # HTTP fetch should NOT have been called
    mock_fetch.assert_not_called()
    
    # Verify source is marked failed and resolved_url is still NULL
    await test_db.refresh(source)
    assert source.resolved_url is None, (
        f"Expected resolved_url to remain NULL when late resolution fails, "
        f"but got {source.resolved_url}"
    )
    assert source.status == SourceStatus.failed_in_download, (
        f"Expected status failed_in_download, got {source.status}"
    )


@pytest.mark.asyncio
async def test_download_with_resolved_url_works(test_db):
    """
    CONTROL: Verify normal case still works.
    
    When a source has resolved_url set, it should be processed normally.
    """
    source = SourceGoogleNews(
        google_news_id="test-with-resolved",
        google_news_url="https://news.google.com/articles/test456",
        resolved_url="https://example.com/article",  # Decoder succeeded
        headline="Tiroteio deixa dois mortos na Zona Norte",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    maker = _TestSessionMaker(test_db)
    html = "<html><body>Dois mortos em tiroteio.</body></html>"
    content = "Dois mortos em tiroteio."
    
    with (
        patch("app.services.download.async_session_maker", maker),
        patch("app.services.diagnostics.async_session_maker", maker),
        patch("app.services.download._fetch_html", new=AsyncMock(return_value=(200, html))),
        patch("app.services.download.extract_content_and_metadata", return_value=(content, None)),
        patch("app.services.download.classify_article_content", new=AsyncMock()),
        patch("app.services.download.passes_content_gate", return_value=True),
        patch("app.services.diagnostics.record_attempt", new=AsyncMock()),
    ):
        result = await download_classified_sources(limit=10)
    
    # This should work (and does work currently)
    assert result["processed"] == 1
    assert result["successful"] == 1
