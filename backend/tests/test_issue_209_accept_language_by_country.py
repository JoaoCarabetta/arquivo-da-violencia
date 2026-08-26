"""Tests for Accept-Language by source country (issue #209).

Accept-Language should follow source country, not URL TLD.
When a URL has no country TLD (e.g., news.google.com), the language
must come from the source's country field, not default to Brazilian Portuguese.
"""

from unittest.mock import AsyncMock, patch, ANY
import pytest

from app.services.download import download_source_content, DownloadOutcome


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
        "google_news_id": "test-id",
        "google_news_url": "https://news.example/article",
        "resolved_url": "https://news.example/article",
        "headline": "Hombre muerto en tiroteo",
        "status": SourceStatus.ready_for_download,
        "country": "AR",  # Default to Argentina
    }
    defaults.update(kwargs)
    return SourceGoogleNews(**defaults)


@pytest.mark.asyncio
async def test_argentina_source_with_google_news_url_sends_spanish(download_db):
    """
    Argentina source with news.google.com URL sends Spanish Accept-Language.
    
    Issue #209: A news.google.com URL has no .ar ending, so the old code
    would default to Brazilian Portuguese. This test verifies the fix:
    Accept-Language comes from country=AR, not from URL TLD.
    """
    source = _source(
        google_news_id="ar-google-news",
        resolved_url="https://news.google.com/articles/xyz",
        country="AR",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article content</body></html>"
    content = "Un hombre fue asesinado en la ciudad."

    mock_fetch = AsyncMock(return_value=(200, html))
    
    with patch(
        "app.services.download._fetch_html",
        mock_fetch,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    # Verify _fetch_html was called with AR country
    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args is not None, "_fetch_html should have been called"
    # After fix, _fetch_html will accept (url, country) signature
    assert len(call_args.args) == 2, "Should pass url and country"
    assert call_args.args[1] == "AR", "Should pass source country to _fetch_html"


@pytest.mark.asyncio
async def test_brazil_source_sends_brazilian_portuguese(download_db):
    """
    Brazil source sends Brazilian Portuguese Accept-Language.
    """
    source = _source(
        google_news_id="br-source",
        resolved_url="https://g1.globo.com/article",
        country="BR",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article content</body></html>"
    content = "Um homem foi morto a tiros na cidade."

    mock_fetch = AsyncMock(return_value=(200, html))
    
    with patch(
        "app.services.download._fetch_html",
        mock_fetch,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args is not None
    assert len(call_args.args) == 2
    assert call_args.args[1] == "BR"


@pytest.mark.asyncio
async def test_chile_source_sends_spanish(download_db):
    """
    Chile source sends Spanish Accept-Language.
    """
    source = _source(
        google_news_id="cl-source",
        resolved_url="https://example.com/article",
        country="CL",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article content</body></html>"
    content = "Hombre muerto en tiroteo."

    mock_fetch = AsyncMock(return_value=(200, html))
    
    with patch(
        "app.services.download._fetch_html",
        mock_fetch,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args is not None
    assert len(call_args.args) == 2
    assert call_args.args[1] == "CL"


@pytest.mark.asyncio
async def test_guyana_source_sends_english(download_db):
    """
    Guyana source sends English Accept-Language.
    """
    source = _source(
        google_news_id="gy-source",
        resolved_url="https://example.com/article",
        country="GY",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article content</body></html>"
    content = "Man killed in shooting."

    mock_fetch = AsyncMock(return_value=(200, html))
    
    with patch(
        "app.services.download._fetch_html",
        mock_fetch,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args is not None
    assert len(call_args.args) == 2
    assert call_args.args[1] == "GY"


@pytest.mark.asyncio
async def test_suriname_source_sends_dutch(download_db):
    """
    Suriname source sends Dutch Accept-Language.
    """
    source = _source(
        google_news_id="sr-source",
        resolved_url="https://example.com/article",
        country="SR",
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article content</body></html>"
    content = "Man gedood in schietpartij."

    mock_fetch = AsyncMock(return_value=(200, html))
    
    with patch(
        "app.services.download._fetch_html",
        mock_fetch,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args is not None
    assert len(call_args.args) == 2
    assert call_args.args[1] == "SR"


@pytest.mark.asyncio
async def test_bare_com_url_uses_source_country_not_default(download_db):
    """
    A URL with no country TLD (.com) uses source country, not default Portuguese.
    
    Issue #209: URLs without country endings (like news.google.com or example.com)
    must NOT default to Brazilian Portuguese. Language comes from source country.
    """
    source = _source(
        google_news_id="ar-bare-com",
        resolved_url="https://example.com/article",
        country="AR",  # Argentina source
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>article content</body></html>"
    content = "Hombre muerto en Buenos Aires."

    mock_fetch = AsyncMock(return_value=(200, html))
    
    with patch(
        "app.services.download._fetch_html",
        mock_fetch,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=(content, None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args
    assert call_args is not None
    assert len(call_args.args) == 2
    # The key assertion: country comes from source, not URL
    assert call_args.args[1] == "AR", "Should use source country AR, not default to BR"


def test_get_accept_language_for_country_argentina():
    """Accept-Language helper returns Spanish for Argentina."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("AR")
    assert result == "es,es-419;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6"


def test_get_accept_language_for_country_brazil():
    """Accept-Language helper returns Brazilian Portuguese for Brazil."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("BR")
    assert result == "pt-BR,pt;q=0.9,en;q=0.8"


def test_get_accept_language_for_country_chile():
    """Accept-Language helper returns Spanish for Chile."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("CL")
    assert result == "es,es-419;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6"


def test_get_accept_language_for_country_guyana():
    """Accept-Language helper returns English for Guyana."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("GY")
    assert result == "en,en-US;q=0.9,es;q=0.8,pt;q=0.7"


def test_get_accept_language_for_country_suriname():
    """Accept-Language helper returns Dutch for Suriname."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("SR")
    assert result == "nl,nl-NL;q=0.9,en;q=0.8,pt;q=0.7"


def test_get_accept_language_for_country_bolivia():
    """Accept-Language helper returns Spanish for Bolivia."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("BO")
    assert result == "es,es-419;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6"


def test_get_accept_language_for_country_colombia():
    """Accept-Language helper returns Spanish for Colombia."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("CO")
    assert result == "es,es-419;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6"


def test_get_accept_language_for_country_ecuador():
    """Accept-Language helper returns Spanish for Ecuador."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country("EC")
    assert result == "es,es-419;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6"


def test_get_accept_language_for_country_null_defaults_to_brazil():
    """Accept-Language helper defaults to Brazilian Portuguese when country is None."""
    from app.services.download import get_accept_language_for_country
    
    result = get_accept_language_for_country(None)
    assert result == "pt-BR,pt;q=0.9,en;q=0.8"
