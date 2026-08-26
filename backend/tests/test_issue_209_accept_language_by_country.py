"""Tests for Accept-Language by source country (issue #209).

Accept-Language should follow source country, not URL TLD.
When a URL has no country TLD (e.g., news.google.com), the language
must come from the source's country field, not default to Brazilian Portuguese.

Critical: Tests must verify the actual HTTP headers sent to httpx, not just
the country argument. Mocking _fetch_html is insufficient to catch regressions
where TLD sniffing is reintroduced inside _fetch_html.
"""

from unittest.mock import AsyncMock, patch, ANY, MagicMock
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
async def test_argentina_news_google_com_sends_spanish_header_not_portuguese(download_db):
    """
    Integration test: Argentina source with news.google.com sends Spanish in HTTP header.
    
    Issue #209 acceptance: Verify the actual Accept-Language HTTP header sent to httpx
    is Spanish (es,es-419), not Brazilian Portuguese (pt-BR), when source country is AR
    and URL has no .ar ending.
    
    This test does NOT mock _fetch_html or get_accept_language_for_country.
    It mocks httpx.AsyncClient to capture the headers actually sent.
    
    If someone reintroduces TLD sniffing inside _fetch_html, this test will fail.
    """
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="ar-news-google",
        resolved_url="https://news.google.com/articles/xyz123",
        country="AR",
        status=SourceStatus.ready_for_download,
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>Un hombre fue asesinado en Buenos Aires.</body></html>"
    
    # Mock httpx.AsyncClient to capture the headers
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()
    
    captured_headers = {}
    
    async def mock_get(url):
        # Capture headers from the client's headers attribute
        return mock_response
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    def capture_client_init(follow_redirects, timeout, headers):
        captured_headers.update(headers)
        return mock_client
    
    with patch(
        "app.services.download.httpx.AsyncClient",
        side_effect=capture_client_init,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=("Un hombre fue asesinado.", None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    # Assert the Accept-Language header is Spanish, not Brazilian Portuguese
    assert "Accept-Language" in captured_headers
    accept_lang = captured_headers["Accept-Language"]
    
    # Spanish must be primary (appears first)
    assert accept_lang.startswith("es"), \
        f"Expected Spanish (es) as primary language, got: {accept_lang}"
    
    # Brazilian Portuguese must NOT be primary
    assert not accept_lang.startswith("pt-BR"), \
        f"Brazilian Portuguese should not be primary for AR source, got: {accept_lang}"
    
    # Full string check
    assert accept_lang == "es,es-419;q=0.9,pt-BR;q=0.8,pt;q=0.7,en;q=0.6", \
        f"Expected Spanish Accept-Language, got: {accept_lang}"


@pytest.mark.asyncio
async def test_brazil_bare_com_url_sends_portuguese_header(download_db):
    """
    Integration test: Brazil source with bare .com URL sends Brazilian Portuguese header.
    
    Verifies that when country=BR and URL has no .br ending, the Accept-Language
    header is Brazilian Portuguese (pt-BR), not Spanish.
    
    This test does NOT mock _fetch_html or get_accept_language_for_country.
    """
    from app.models.source_google_news import SourceStatus

    source = _source(
        google_news_id="br-bare-com",
        resolved_url="https://example.com/article/12345",
        country="BR",
        status=SourceStatus.ready_for_download,
    )
    download_db.add(source)
    await download_db.commit()
    await download_db.refresh(source)

    html = "<html><body>Um homem foi morto a tiros na cidade.</body></html>"
    
    # Mock httpx.AsyncClient to capture the headers
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()
    
    captured_headers = {}
    
    async def mock_get(url):
        return mock_response
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=mock_get)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    def capture_client_init(follow_redirects, timeout, headers):
        captured_headers.update(headers)
        return mock_client
    
    with patch(
        "app.services.download.httpx.AsyncClient",
        side_effect=capture_client_init,
    ), patch(
        "app.services.download.extract_content_and_metadata",
        return_value=("Um homem foi morto.", None),
    ), patch(
        "app.services.download.classify_article_content",
    ), patch(
        "app.services.download.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        outcome = await download_source_content(source.id)

    # Assert the Accept-Language header is Brazilian Portuguese
    assert "Accept-Language" in captured_headers
    accept_lang = captured_headers["Accept-Language"]
    
    # Brazilian Portuguese must be primary
    assert accept_lang.startswith("pt-BR"), \
        f"Expected Brazilian Portuguese (pt-BR) as primary, got: {accept_lang}"
    
    # Spanish must NOT be primary
    assert not accept_lang.startswith("es"), \
        f"Spanish should not be primary for BR source, got: {accept_lang}"
    
    # Full string check
    assert accept_lang == "pt-BR,pt;q=0.9,en;q=0.8", \
        f"Expected Brazilian Portuguese Accept-Language, got: {accept_lang}"


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
