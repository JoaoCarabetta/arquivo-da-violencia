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
async def test_download_skips_null_resolved_url(test_db):
    """
    RED TEST: Verify the bug exists.
    
    When a source has:
    - status = ready_for_download
    - resolved_url = NULL
    - google_news_url present
    
    download_classified_sources should process it, but currently skips it
    due to the WHERE resolved_url IS NOT NULL filter.
    """
    # Create a source that simulates decoder failure:
    # resolved_url is NULL but google_news_url is present
    source = SourceGoogleNews(
        google_news_id="test-null-resolved",
        google_news_url="https://news.google.com/articles/test123",
        resolved_url=None,  # Decoder returned None
        headline="Homem é morto a tiros em operação policial",
        status=SourceStatus.ready_for_download,
        is_violent_death=True,
    )
    
    test_db.add(source)
    await test_db.commit()
    await test_db.refresh(source)
    
    # Mock the download flow to prevent actual HTTP calls
    maker = _TestSessionMaker(test_db)
    html = "<html><body>Homem foi morto durante operação policial.</body></html>"
    content = "Homem foi morto durante operação policial."
    
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
    
    # THE BUG: This should process 1 source, but currently processes 0
    # because the SQL filter excludes rows with resolved_url IS NULL
    assert result["processed"] == 1, (
        f"Expected to process 1 source with NULL resolved_url, "
        f"but got {result['processed']}. This is the bug from issue #171."
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
