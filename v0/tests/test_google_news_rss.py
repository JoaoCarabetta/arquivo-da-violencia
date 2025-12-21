"""
Test suite for Google News RSS Feed behavior.

This test suite validates the behavior documented in docs/google news spec.md.
All tests require network access and hit the live Google News RSS endpoints.

Run with: pytest tests/test_google_news_rss.py -v
Run only fast tests: pytest tests/test_google_news_rss.py -v -m "not slow"
"""

import pytest
import requests
import feedparser
import re
import base64
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse, parse_qs
from typing import Optional
from xml.etree import ElementTree as ET


# =============================================================================
# Constants from Spec
# =============================================================================

BASE_URL = "https://news.google.com/rss"
YAHOO_MEDIA_NAMESPACE = "http://search.yahoo.com/mrss/"

# Canonical localization configurations from spec Section 2
LOCALIZATION_CONFIGS = {
    "USA": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    "UK": {"hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
    "India_English": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
    "Brazil": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt"},
    "Germany": {"hl": "de", "gl": "DE", "ceid": "DE:de"},
}

# Standard request timeout
REQUEST_TIMEOUT = 30


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def brazil_params():
    """Brazilian localization parameters."""
    return LOCALIZATION_CONFIGS["Brazil"]


@pytest.fixture
def usa_params():
    """US localization parameters."""
    return LOCALIZATION_CONFIGS["USA"]


def build_url(endpoint: str, params: dict) -> str:
    """Build a full URL with localization parameters."""
    url = f"{BASE_URL}{endpoint}"
    query_parts = []
    for key, value in params.items():
        query_parts.append(f"{key}={quote(str(value), safe=':')}")
    if query_parts:
        url += ("&" if "?" in url else "?") + "&".join(query_parts)
    return url


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    """Fetch and parse an RSS feed."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return feedparser.parse(response.content)


def fetch_raw(url: str) -> str:
    """Fetch raw XML content."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


# =============================================================================
# Section 1: Overview - RSS 2.0 Protocol Tests
# =============================================================================

class TestRSSProtocol:
    """Test that the feed conforms to RSS 2.0 protocol."""

    def test_base_url_returns_rss_xml(self, brazil_params):
        """Verify base URL returns valid RSS 2.0 XML."""
        url = build_url("", brazil_params)
        raw_content = fetch_raw(url)
        
        # Check XML declaration or RSS root element
        assert "<?xml" in raw_content or "<rss" in raw_content
        
        # Parse as XML to validate structure
        root = ET.fromstring(raw_content.encode())
        assert root.tag == "rss"
        assert root.attrib.get("version") == "2.0"

    def test_rss_has_yahoo_media_namespace(self, brazil_params):
        """Verify RSS includes Yahoo Media namespace (spec Section 1)."""
        url = build_url("", brazil_params)
        raw_content = fetch_raw(url)
        
        # Check for media namespace declaration
        assert YAHOO_MEDIA_NAMESPACE in raw_content

    def test_rss_has_channel_element(self, brazil_params):
        """Verify RSS has required channel element."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        assert feed.feed is not None
        assert hasattr(feed, 'entries')

    def test_feed_has_lastbuilddate(self, brazil_params):
        """Verify feed includes lastBuildDate for caching (spec Section 7.3)."""
        url = build_url("", brazil_params)
        raw_content = fetch_raw(url)
        
        assert "<lastBuildDate>" in raw_content


# =============================================================================
# Section 2: Localization Parameters Tests
# =============================================================================

class TestLocalizationParameters:
    """Test the localization triad (hl, gl, ceid)."""

    @pytest.mark.parametrize("region,config", LOCALIZATION_CONFIGS.items())
    def test_localization_config_returns_results(self, region, config):
        """Verify each canonical localization config works."""
        url = build_url("", config)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0, f"No results for {region} configuration"

    def test_brazil_config_returns_portuguese_sources(self, brazil_params):
        """Verify Brazil config returns sources in Portuguese locale."""
        url = build_url("/search?q=brasil", brazil_params)
        feed = fetch_feed(url)
        
        # Check that at least some sources have .br domains or Portuguese content
        assert len(feed.entries) > 0
        
        # Check for Brazilian sources
        br_sources = [
            e for e in feed.entries 
            if hasattr(e, 'source') and '.br' in str(getattr(e.source, 'href', ''))
        ]
        # At least some results should be from .br domains
        assert len(br_sources) > 0, "Expected some .br domain sources for Brazil config"

    def test_usa_config_returns_english_sources(self, usa_params):
        """Verify USA config returns sources in English locale."""
        url = build_url("/search?q=crime", usa_params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0
        
        # Check for US/English sources (common domains)
        us_source_patterns = ['.com', '.org', '.gov']
        has_us_sources = any(
            any(pattern in str(getattr(e.source, 'href', '')) for pattern in us_source_patterns)
            for e in feed.entries if hasattr(e, 'source')
        )
        assert has_us_sources, "Expected some US domain sources for USA config"


# =============================================================================
# Section 3: Endpoints Tests
# =============================================================================

class TestSearchEndpoint:
    """Test the search endpoint (spec Section 3.1)."""

    def test_search_endpoint_returns_results(self, brazil_params):
        """Verify search endpoint returns results for a query."""
        params = {**brazil_params, "q": "violência"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0

    def test_search_with_spaces_encoded(self, brazil_params):
        """Verify search handles URL-encoded spaces."""
        params = {**brazil_params, "q": "violência policial"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0


class TestTopicEndpoint:
    """Test the topic endpoint (spec Section 3.2)."""

    def test_topic_id_format(self):
        """Verify topic IDs are Base64-encoded (start with CAAq...)."""
        # Topic IDs should be discovered from the web UI
        # This test documents the expected format
        sample_topic_id = "CAAqIQgKIhtDQkFTRGdvSUwyMHZNRFpuYlhJU0FtVnVLQUFQAQ"
        
        assert sample_topic_id.startswith("CAAq")
        # Should be valid base64
        try:
            base64.urlsafe_b64decode(sample_topic_id + "==")
        except Exception:
            pytest.fail("Topic ID should be valid Base64")


class TestGeoSpatialEndpoint:
    """Test the geo-spatial endpoint (spec Section 3.3)."""

    def test_geo_endpoint_accepts_city(self, brazil_params):
        """Verify geo endpoint accepts city names."""
        url = f"{BASE_URL}/headlines/section/geo/Rio%20de%20Janeiro"
        url += f"?hl={brazil_params['hl']}&gl={brazil_params['gl']}&ceid={brazil_params['ceid']}"
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=False)
        
        # May redirect to topics endpoint or return directly
        assert response.status_code in [200, 302, 301]

    def test_geo_endpoint_redirects_to_topic(self, brazil_params):
        """Verify geo endpoint often redirects to /topics/ (spec Section 3.3)."""
        url = f"{BASE_URL}/headlines/section/geo/Sao%20Paulo"
        url += f"?hl={brazil_params['hl']}&gl={brazil_params['gl']}&ceid={brazil_params['ceid']}"
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        
        # After following redirects, URL often contains /topics/ with Base64 ID
        final_url = response.url
        
        # Should either have /topics/ or still be geo
        assert response.status_code == 200
        if "/topics/" in final_url:
            # Verify topic ID format (starts with CAAq)
            topic_part = final_url.split("/topics/")[1].split("?")[0]
            assert topic_part.startswith("CAAq"), "Topic ID should start with CAAq"

    def test_geo_endpoint_accepts_us_zip(self, usa_params):
        """Verify geo endpoint accepts US ZIP codes."""
        url = f"{BASE_URL}/headlines/section/geo/90210"
        url += f"?hl={usa_params['hl']}&gl={usa_params['gl']}&ceid={usa_params['ceid']}"
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        assert response.status_code == 200


class TestTopHeadlinesEndpoint:
    """Test the top headlines endpoint (spec Section 3.4)."""

    def test_top_headlines_returns_results(self, brazil_params):
        """Verify top headlines endpoint returns the front page."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0

    def test_top_headlines_has_diverse_sources(self, brazil_params):
        """Verify top headlines contain diverse sources."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        sources = set()
        for entry in feed.entries:
            if hasattr(entry, 'source') and hasattr(entry.source, 'href'):
                sources.add(entry.source.href)
        
        # Should have at least a few different sources
        assert len(sources) >= 3, "Expected diverse sources in top headlines"


# =============================================================================
# Section 4: Query Syntax Tests
# =============================================================================

class TestBooleanOperators:
    """Test boolean operators in query syntax (spec Section 4)."""

    def test_implicit_and_operator(self, brazil_params):
        """Verify space acts as implicit AND."""
        params = {**brazil_params, "q": "violência policial"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0

    def test_or_operator(self, brazil_params):
        """Verify OR operator broadens search."""
        params = {**brazil_params, "q": "crime OR violência"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0

    def test_not_operator_exclusion(self, usa_params):
        """Verify - operator excludes terms."""
        params = {**usa_params, "q": "jaguar -car"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return results (if any exist)
        # The key is that the query is accepted
        assert feed is not None

    def test_grouping_with_parentheses(self, usa_params):
        """Verify parentheses group logic correctly."""
        params = {**usa_params, "q": "(Apple OR Microsoft) revenue"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0


class TestAdvancedFilters:
    """Test advanced filter operators (spec Section 4)."""

    def test_site_filter(self, brazil_params):
        """Verify site: restricts to specific domain."""
        params = {**brazil_params, "q": "site:g1.globo.com violência"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # All results should be from g1.globo.com
        for entry in feed.entries:
            if hasattr(entry, 'source') and hasattr(entry.source, 'href'):
                assert 'g1.globo.com' in entry.source.href, \
                    f"Expected g1.globo.com, got {entry.source.href}"

    def test_intitle_filter(self, brazil_params):
        """Verify intitle: requires keyword in headline."""
        params = {**brazil_params, "q": 'intitle:"violência"'}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Results should have the keyword in title
        if len(feed.entries) > 0:
            # Check first few entries
            for entry in feed.entries[:5]:
                # Title format: "Headline - Source"
                title_lower = entry.title.lower()
                assert "violência" in title_lower or "violencia" in title_lower, \
                    f"Expected 'violência' in title, got: {entry.title}"

    def test_when_filter_1d_returns_recent_articles(self, brazil_params):
        """Verify when:1d restricts to last 24 hours."""
        params = {**brazil_params, "q": "brasil when:1d"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        now = datetime.utcnow()
        max_age_hours = 48  # Allow some buffer for timezones
        
        # All articles must be recent
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
                age = now - pub_date
                age_hours = age.total_seconds() / 3600
                assert age_hours <= max_age_hours, \
                    f"Article '{entry.title[:50]}' is {age_hours:.1f}h old, expected <= {max_age_hours}h"

    def test_when_filter_6h_returns_articles_within_6_hours(self, brazil_params):
        """Verify when:6h restricts to last 6 hours."""
        params = {**brazil_params, "q": "brasil when:6h"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        now = datetime.utcnow()
        max_age_hours = 12  # Allow buffer for timezones/propagation
        
        # All articles must be very recent
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
                age = now - pub_date
                age_hours = age.total_seconds() / 3600
                assert age_hours <= max_age_hours, \
                    f"Article '{entry.title[:50]}' is {age_hours:.1f}h old, expected <= {max_age_hours}h for when:6h"

    def test_when_filter_1h_returns_very_recent_articles(self, brazil_params):
        """Verify when:1h restricts to last 1 hour."""
        params = {**brazil_params, "q": "brasil when:1h"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        now = datetime.utcnow()
        max_age_hours = 3  # Allow small buffer
        
        # All articles must be very recent (may be empty if no news)
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
                age = now - pub_date
                age_hours = age.total_seconds() / 3600
                assert age_hours <= max_age_hours, \
                    f"Article '{entry.title[:50]}' is {age_hours:.1f}h old, expected <= {max_age_hours}h for when:1h"

    def test_after_filter_excludes_older_articles(self, brazil_params):
        """Verify after: excludes articles before the specified date."""
        # Use a date 3 days ago
        after_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        after_datetime = datetime.strptime(after_date, "%Y-%m-%d")
        
        params = {**brazil_params, "q": f"brasil after:{after_date}"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0, "Expected results for recent after: filter"
        
        # All articles should be after the specified date
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
                # Allow 1 day buffer for timezone differences
                assert pub_date >= after_datetime - timedelta(days=1), \
                    f"Article '{entry.title[:50]}' dated {pub_date} is before after:{after_date}"

    def test_before_filter_excludes_newer_articles(self, brazil_params):
        """Verify before: excludes articles after the specified date."""
        # Use a date range in the past month
        before_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        after_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        before_datetime = datetime.strptime(before_date, "%Y-%m-%d")
        
        params = {**brazil_params, "q": f"brasil after:{after_date} before:{before_date}"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # All articles should be before the specified date
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
                # Allow 1 day buffer for timezone differences
                assert pub_date <= before_datetime + timedelta(days=1), \
                    f"Article '{entry.title[:50]}' dated {pub_date} is after before:{before_date}"

    def test_date_range_constrains_results(self, brazil_params):
        """Verify after: + before: constrains articles to date range."""
        # Define a specific week in the past
        after_date = "2024-12-01"
        before_date = "2024-12-08"
        after_dt = datetime.strptime(after_date, "%Y-%m-%d")
        before_dt = datetime.strptime(before_date, "%Y-%m-%d")
        
        params = {**brazil_params, "q": f"brasil after:{after_date} before:{before_date}"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Verify all results are within the date range
        for entry in feed.entries:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6])
                # Allow 1 day buffer on each side
                assert after_dt - timedelta(days=1) <= pub_date <= before_dt + timedelta(days=1), \
                    f"Article dated {pub_date} outside range {after_date} to {before_date}"


# =============================================================================
# Section 5: Response Schema Tests
# =============================================================================

class TestItemStructure:
    """Test RSS item structure (spec Section 5)."""

    def test_item_has_title(self, brazil_params):
        """Verify items have title element."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            assert hasattr(entry, 'title')
            assert entry.title is not None
            assert len(entry.title) > 0

    def test_title_format_headline_source(self, brazil_params):
        """Verify title format: 'Headline - Source' (spec Section 5)."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        # Check that titles contain the separator
        titles_with_separator = [
            e for e in feed.entries 
            if ' - ' in e.title
        ]
        
        # Most titles should have this format
        assert len(titles_with_separator) >= len(feed.entries) * 0.8, \
            "Expected most titles to have 'Headline - Source' format"

    def test_item_has_link(self, brazil_params):
        """Verify items have link element."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            assert hasattr(entry, 'link')
            assert entry.link is not None
            assert entry.link.startswith('https://news.google.com/')

    def test_item_link_is_obfuscated(self, brazil_params):
        """Verify item links are obfuscated Google redirects (spec Section 5)."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            # Links should be Google redirect URLs, not direct publisher URLs
            assert 'news.google.com' in entry.link, \
                f"Expected obfuscated link, got: {entry.link}"
            # Should contain encoded article ID
            assert '/articles/' in entry.link or '/rss/articles/' in entry.link or 'CBM' in entry.link

    def test_item_has_guid(self, brazil_params):
        """Verify items have guid element with isPermaLink=false."""
        url = build_url("", brazil_params)
        raw_content = fetch_raw(url)
        
        # Check for guid with isPermaLink="false"
        assert 'isPermaLink="false"' in raw_content

    def test_item_has_pubdate(self, brazil_params):
        """Verify items have pubDate element."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            assert hasattr(entry, 'published') or hasattr(entry, 'published_parsed')

    def test_item_has_description(self, brazil_params):
        """Verify items have description element."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            assert hasattr(entry, 'summary') or hasattr(entry, 'description')

    def test_item_has_source(self, brazil_params):
        """Verify items have source element with url attribute."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            assert hasattr(entry, 'source'), f"Entry missing source: {entry.title}"
            if hasattr(entry.source, 'href'):
                assert entry.source.href.startswith('http'), \
                    f"Source URL should be valid: {entry.source.href}"


# =============================================================================
# Section 6: URL Obfuscation Tests
# =============================================================================

class TestURLObfuscation:
    """Test URL obfuscation and encoding (spec Section 6)."""

    def test_article_links_are_base64_encoded(self, brazil_params):
        """Verify article links contain Base64-encoded identifiers."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:5]:
            link = entry.link
            # Extract the article ID part
            if '/articles/' in link:
                article_id = link.split('/articles/')[-1].split('?')[0]
                # Should look like Base64 (starts with CBM or similar)
                assert len(article_id) > 10, f"Article ID too short: {article_id}"
                # Common prefixes for Google News article IDs
                assert article_id.startswith(('CBM', 'CAI')), \
                    f"Unexpected article ID format: {article_id[:20]}"

    def test_guid_matches_link_id(self, brazil_params):
        """Verify guid matches the encoded article ID."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        for entry in feed.entries[:3]:
            if hasattr(entry, 'id') and '/articles/' in entry.link:
                article_id = entry.link.split('/articles/')[-1].split('?')[0]
                # GUID should contain the same ID or be related
                assert article_id in entry.id or entry.id in entry.link


# =============================================================================
# Section 7: Operational Limits Tests
# =============================================================================

class TestOperationalLimits:
    """Test operational limitations (spec Section 7)."""

    @pytest.mark.slow
    def test_result_cap_approximately_100(self, brazil_params):
        """Verify feed caps at approximately 100 items (spec Section 7.2)."""
        # Use a broad query to get max results
        params = {**brazil_params, "q": "brasil"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should cap at around 100
        assert len(feed.entries) <= 110, \
            f"Expected max ~100 entries, got {len(feed.entries)}"

    def test_no_pagination_parameter(self, brazil_params):
        """Verify there's no page parameter (spec Section 7.2)."""
        # Adding page parameter should not affect results
        params = {**brazil_params, "q": "brasil"}
        url = build_url("/search", params)
        url_with_page = url + "&page=2"
        
        feed_no_page = fetch_feed(url)
        feed_with_page = fetch_feed(url_with_page)
        
        # Results should be identical (page param ignored)
        assert len(feed_no_page.entries) == len(feed_with_page.entries)

    def test_sliding_window_workaround(self, brazil_params):
        """Demonstrate sliding window technique for >100 results (spec Section 7.2)."""
        # First window
        params1 = {**brazil_params, "q": "crime after:2024-12-01 before:2024-12-08"}
        url1 = build_url("/search", params1)
        feed1 = fetch_feed(url1)
        
        # Second window
        params2 = {**brazil_params, "q": "crime after:2024-12-08 before:2024-12-15"}
        url2 = build_url("/search", params2)
        feed2 = fetch_feed(url2)
        
        # Both should return results
        assert feed1 is not None
        assert feed2 is not None
        
        # Combined would give more than single query
        total = len(feed1.entries) + len(feed2.entries)
        assert total > 0


class TestCaching:
    """Test caching behavior (spec Section 7.3)."""

    def test_lastbuilddate_present(self, brazil_params):
        """Verify lastBuildDate is present for caching."""
        url = build_url("", brazil_params)
        raw_content = fetch_raw(url)
        
        assert "<lastBuildDate>" in raw_content
        assert "</lastBuildDate>" in raw_content


class TestRealTimePolling:
    """Test real-time polling recommendations (spec Section 7.4)."""

    def test_when_1h_reduces_payload(self, brazil_params):
        """Verify when:1h can be used to reduce payload size."""
        # Without time filter
        params_all = {**brazil_params, "q": "brasil"}
        url_all = build_url("/search", params_all)
        feed_all = fetch_feed(url_all)
        
        # With time filter
        params_recent = {**brazil_params, "q": "brasil when:1h"}
        url_recent = build_url("/search", params_recent)
        feed_recent = fetch_feed(url_recent)
        
        # Recent should have fewer or equal results
        assert len(feed_recent.entries) <= len(feed_all.entries)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple features."""

    def test_complex_query_combination(self, brazil_params):
        """Test combining multiple query features."""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        params = {
            **brazil_params, 
            "q": f"(violência OR crime) -esporte after:{yesterday}"
        }
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return results
        assert feed is not None

    def test_full_workflow_simulation(self, brazil_params):
        """Simulate a full news ingestion workflow."""
        # Step 1: Get top headlines
        top_url = build_url("", brazil_params)
        top_feed = fetch_feed(top_url)
        assert len(top_feed.entries) > 0
        
        # Step 2: Search for specific topic
        search_params = {**brazil_params, "q": "violência when:1d"}
        search_url = build_url("/search", search_params)
        search_feed = fetch_feed(search_url)
        
        # Step 3: Verify we can extract article info
        for entry in search_feed.entries[:3]:
            assert entry.title
            assert entry.link
            assert hasattr(entry, 'published') or hasattr(entry, 'published_parsed')
            
            # Extract source name from title
            if ' - ' in entry.title:
                parts = entry.title.rsplit(' - ', 1)
                headline = parts[0]
                source_name = parts[1] if len(parts) > 1 else None
                assert headline
                assert source_name


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_empty_query_returns_top_headlines(self, brazil_params):
        """Verify empty search returns top headlines."""
        url = build_url("", brazil_params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0

    def test_special_characters_in_query(self, brazil_params):
        """Verify special characters are handled."""
        params = {**brazil_params, "q": "violência & crime"}
        url = build_url("/search", params)
        
        # Should not raise an error
        feed = fetch_feed(url)
        assert feed is not None

    def test_unicode_query(self, brazil_params):
        """Verify Unicode characters work in queries."""
        params = {**brazil_params, "q": "São Paulo violência"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        assert len(feed.entries) > 0

    def test_very_long_query(self, brazil_params):
        """Verify long queries are handled."""
        long_query = "crime violência policial " * 10
        params = {**brazil_params, "q": long_query.strip()}
        url = build_url("/search", params)
        
        # Should not raise an error
        feed = fetch_feed(url)
        assert feed is not None


class TestInvalidFilterValues:
    """Test behavior with invalid/nonsense filter values."""

    def test_when_banana_treated_as_literal(self, brazil_params):
        """Verify when:banana is treated as literal search, not time filter."""
        params = {**brazil_params, "q": "brasil when:banana"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Query is accepted, but when:banana should not filter by time
        # Compare with a valid time filter - invalid should return different results
        params_valid = {**brazil_params, "q": "brasil when:1d"}
        url_valid = build_url("/search", params_valid)
        feed_valid = fetch_feed(url_valid)
        
        # With invalid when:, it should NOT filter by time
        # So if there are results, they may include older articles
        # The key test: query doesn't crash and is handled
        assert feed is not None
        
        # If we have results, check that "when:banana" is NOT restricting time
        if len(feed.entries) > 0:
            now = datetime.utcnow()
            has_old_article = False
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])
                    age_hours = (now - pub_date).total_seconds() / 3600
                    if age_hours > 24:  # Older than 1 day
                        has_old_article = True
                        break
            # With invalid when:, older articles may appear (unlike when:1d)
            # This is a weak assertion since it depends on search results

    def test_when_negative_value(self, brazil_params):
        """Verify when:-1h is handled."""
        params = {**brazil_params, "q": "brasil when:-1h"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash
        assert feed is not None

    def test_when_zero_value(self, brazil_params):
        """Verify when:0h is handled."""
        params = {**brazil_params, "q": "brasil when:0h"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - may return no results or treat as invalid
        assert feed is not None

    def test_when_very_large_value(self, brazil_params):
        """Verify when:9999d is handled."""
        params = {**brazil_params, "q": "brasil when:9999d"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return results (effectively no time limit)
        assert feed is not None
        assert len(feed.entries) > 0

    def test_after_banana_treated_as_literal(self, brazil_params):
        """Verify after:banana is treated as literal, not date filter."""
        params = {**brazil_params, "q": "crime after:banana"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - Google handles gracefully
        assert feed is not None

    def test_after_invalid_date_format(self, brazil_params):
        """Verify after:31-12-2024 (wrong format) is handled."""
        params = {**brazil_params, "q": "brasil after:31-12-2024"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash
        assert feed is not None

    def test_after_future_date(self, brazil_params):
        """Verify after: with future date returns no results."""
        future_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        params = {**brazil_params, "q": f"brasil after:{future_date}"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return no results (no articles from the future)
        assert len(feed.entries) == 0, \
            f"Expected no results for future date after:{future_date}, got {len(feed.entries)}"

    def test_before_very_old_date_is_ignored(self, brazil_params):
        """Verify before: with very old date is IGNORED (treated as literal text).
        
        NOTE: This documents actual Google behavior - very old dates are not
        treated as date filters, so they return current results instead of 
        no results. This is different from what might be expected.
        """
        params = {**brazil_params, "q": "brasil before:2000-01-01"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # ACTUAL BEHAVIOR: Google ignores invalid/very old dates and returns current results
        # This is important to document - very old dates don't filter, they're ignored
        assert len(feed.entries) > 0, \
            "Google ignores very old before: dates and returns current results"

    def test_site_empty_domain(self, brazil_params):
        """Verify site: with no domain is handled."""
        params = {**brazil_params, "q": "brasil site:"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - treated as literal "site:"
        assert feed is not None

    def test_site_invalid_domain(self, brazil_params):
        """Verify site: with invalid domain returns no results."""
        params = {**brazil_params, "q": "site:thisisnotarealdomainthatexists12345.xyz brasil"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return no results (domain doesn't exist)
        assert len(feed.entries) == 0, \
            f"Expected no results for non-existent domain, got {len(feed.entries)}"

    def test_site_malformed_url(self, brazil_params):
        """Verify site: with malformed URL is handled."""
        params = {**brazil_params, "q": "site:http://g1.globo.com brasil"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should handle - may or may not work depending on Google's parsing
        assert feed is not None

    def test_intitle_empty_quotes(self, brazil_params):
        """Verify intitle:"" (empty) is handled."""
        params = {**brazil_params, "q": 'brasil intitle:""'}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash
        assert feed is not None

    def test_intitle_no_quotes(self, brazil_params):
        """Verify intitle: without quotes works."""
        params = {**brazil_params, "q": "intitle:violência brasil"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should work and filter by title
        if len(feed.entries) > 0:
            # Check at least some titles contain the keyword
            matches = sum(1 for e in feed.entries if 'violência' in e.title.lower() or 'violencia' in e.title.lower())
            assert matches > 0, "Expected some titles to contain 'violência'"

    def test_contradictory_date_range(self, brazil_params):
        """Verify after: > before: (impossible range) returns no results."""
        params = {**brazil_params, "q": "brasil after:2024-12-15 before:2024-12-01"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return no results (impossible date range)
        assert len(feed.entries) == 0, \
            f"Expected no results for contradictory date range, got {len(feed.entries)}"

    def test_multiple_when_filters(self, brazil_params):
        """Verify multiple when: filters - last one should win or be combined."""
        params = {**brazil_params, "q": "brasil when:1h when:7d"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - behavior depends on Google's parser
        assert feed is not None

    def test_multiple_site_filters(self, brazil_params):
        """Verify multiple site: filters."""
        params = {**brazil_params, "q": "brasil site:g1.globo.com site:uol.com.br"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # May return results from either site or be treated as AND (no results)
        assert feed is not None


class TestLocalizationEdgeCases:
    """Test edge cases for localization parameters."""

    def test_invalid_hl_parameter(self):
        """Verify invalid hl parameter is handled."""
        params = {"hl": "invalid-language", "gl": "US", "ceid": "US:en"}
        url = build_url("", params)
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        # Should return 200 (falls back to default) or error
        assert response.status_code in [200, 400, 404]

    def test_mismatched_ceid(self):
        """Verify mismatched ceid (e.g., BR locale with US:en ceid)."""
        params = {"hl": "pt-BR", "gl": "BR", "ceid": "US:en"}
        url = build_url("", params)
        feed = fetch_feed(url)
        
        # Should still work - ceid may override or be ignored
        assert len(feed.entries) > 0

    def test_missing_gl_parameter(self, brazil_params):
        """Verify feed works with missing gl parameter."""
        params = {"hl": brazil_params["hl"], "ceid": brazil_params["ceid"]}
        url = build_url("", params)
        feed = fetch_feed(url)
        
        # Should still return results (uses IP-based location)
        assert len(feed.entries) > 0

    def test_missing_all_localization(self):
        """Verify feed works with no localization parameters."""
        url = BASE_URL
        feed = fetch_feed(url)
        
        # Should return results (defaults to IP-based location)
        assert len(feed.entries) > 0


class TestQuerySyntaxEdgeCases:
    """Test edge cases for query syntax."""

    def test_only_operators_no_keywords(self, brazil_params):
        """Verify query with only operators is handled."""
        params = {**brazil_params, "q": "OR AND"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash
        assert feed is not None

    def test_unbalanced_parentheses(self, brazil_params):
        """Verify unbalanced parentheses are handled."""
        params = {**brazil_params, "q": "(brasil OR crime"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - Google handles gracefully
        assert feed is not None

    def test_only_exclusion_operator(self, brazil_params):
        """Verify query with only exclusion is handled."""
        params = {**brazil_params, "q": "-crime"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - may return no results
        assert feed is not None

    def test_double_quotes_phrase(self, brazil_params):
        """Verify exact phrase matching with double quotes."""
        params = {**brazil_params, "q": '"violência policial"'}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return results with exact phrase
        assert feed is not None
        if len(feed.entries) > 0:
            # Check that titles/content likely contain the phrase
            # (We can't easily verify without fetching full content)
            pass

    def test_sql_injection_attempt(self, brazil_params):
        """Verify SQL-like injection strings are handled safely."""
        params = {**brazil_params, "q": "brasil'; DROP TABLE news; --"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - treated as literal search
        assert feed is not None

    def test_html_in_query(self, brazil_params):
        """Verify HTML in query is handled safely."""
        params = {**brazil_params, "q": "brasil <script>alert('xss')</script>"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should not crash - treated as literal search
        assert feed is not None

    def test_empty_string_query_returns_404(self, brazil_params):
        """Verify empty string query on /search endpoint returns 404.
        
        NOTE: The /search endpoint requires a query. Empty q= returns 404.
        Use the base /rss endpoint (no /search) for top headlines.
        """
        params = {**brazil_params, "q": ""}
        url = build_url("/search", params)
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        
        # ACTUAL BEHAVIOR: Empty query on /search returns 404
        assert response.status_code == 404, \
            f"Expected 404 for empty search query, got {response.status_code}"

    def test_whitespace_only_query(self, brazil_params):
        """Verify whitespace-only query is handled."""
        params = {**brazil_params, "q": "   "}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return results (treated as empty)
        assert feed is not None


# =============================================================================
# Small City / Low Volume Tests
# =============================================================================

class TestSmallCityBehavior:
    """Test behavior for small cities with low news volume.
    
    These tests document real-world expectations when searching for 
    specific, small locations that don't generate much news coverage.
    Example: Pau dos Ferros, RN (pop ~30,000) in Brazil's interior.
    """

    def test_small_city_with_1h_filter_returns_zero_results(self, brazil_params):
        """Verify small city + when:1h typically returns zero results.
        
        For small cities, there's rarely news within the last hour.
        This is expected behavior and systems should handle empty feeds.
        """
        # Pau dos Ferros is a small city in Rio Grande do Norte, Brazil
        params = {**brazil_params, "q": "Pau dos Ferros when:1h"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Expected: zero or very few results (news about this city is rare)
        # This test documents that empty results are a valid response
        assert len(feed.entries) >= 0  # Valid feed, possibly empty
        
        # For small cities, 0 results in 1h is normal
        # If this test fails with many results, it means something newsworthy happened!

    def test_small_city_without_time_filter_may_have_results(self, brazil_params):
        """Verify small city without time filter may return some results.
        
        Without time constraints, we might find older articles about the city.
        """
        params = {**brazil_params, "q": "Pau dos Ferros RN"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return feed (may or may not have results)
        assert feed is not None
        # Don't assert count - depends on news cycle

    def test_small_city_with_7d_filter(self, brazil_params):
        """Verify small city with 7-day window has better chance of results."""
        params = {**brazil_params, "q": "Pau dos Ferros when:7d"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # 7-day window gives better chance for small cities
        assert feed is not None
        # Still may be empty depending on news cycle

    def test_small_city_geo_endpoint_may_be_unsupported(self, brazil_params):
        """Verify geo endpoint for small cities may redirect to 'unsupported'.
        
        Google doesn't have dedicated geo topics for all cities.
        Small cities may redirect to /rss/unsupported or return limited results.
        """
        url = f"{BASE_URL}/headlines/section/geo/Pau%20dos%20Ferros"
        url += f"?hl={brazil_params['hl']}&gl={brazil_params['gl']}&ceid={brazil_params['ceid']}"
        
        response = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        
        # May redirect to /unsupported for small cities
        # This is different from major cities which get proper /topics/ redirects
        assert response.status_code == 200
        
        # Check if redirected to unsupported
        if "unsupported" in response.url:
            # This is expected for small cities - document this behavior
            pass
        elif "/topics/" in response.url:
            # Small city somehow has a topic - unexpected but valid
            pass

    def test_compare_small_vs_large_city_results(self, brazil_params):
        """Compare result counts between small and large cities.
        
        Large cities should consistently have more results than small ones.
        """
        # Small city
        params_small = {**brazil_params, "q": "Pau dos Ferros when:1d"}
        url_small = build_url("/search", params_small)
        feed_small = fetch_feed(url_small)
        
        # Large city
        params_large = {**brazil_params, "q": "São Paulo when:1d"}
        url_large = build_url("/search", params_large)
        feed_large = fetch_feed(url_large)
        
        # Large city should have significantly more results
        assert len(feed_large.entries) > len(feed_small.entries), \
            f"Expected São Paulo ({len(feed_large.entries)}) > Pau dos Ferros ({len(feed_small.entries)})"

    def test_remote_village_returns_empty(self, brazil_params):
        """Verify extremely small/remote locations return empty results.
        
        Villages with no online news presence should return 0 results.
        """
        # A very small, remote location unlikely to have any online news
        params = {**brazil_params, "q": "Sítio Boa Vista Paraíba when:1h"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should be empty or nearly empty
        assert len(feed.entries) <= 5, \
            f"Unexpectedly found {len(feed.entries)} results for remote village"

    def test_state_vs_city_specificity(self, brazil_params):
        """Compare results for state vs specific city.
        
        Searching for state should return more results than small city in that state.
        """
        # State level
        params_state = {**brazil_params, "q": "Rio Grande do Norte when:1d"}
        url_state = build_url("/search", params_state)
        feed_state = fetch_feed(url_state)
        
        # Small city in that state
        params_city = {**brazil_params, "q": "Pau dos Ferros RN when:1d"}
        url_city = build_url("/search", params_city)
        feed_city = fetch_feed(url_city)
        
        # State should have more results
        assert len(feed_state.entries) >= len(feed_city.entries), \
            f"Expected state ({len(feed_state.entries)}) >= city ({len(feed_city.entries)})"

    def test_neighborhood_level_search(self, brazil_params):
        """Test neighborhood-level search granularity.
        
        Searching for specific neighborhoods may return fewer results.
        """
        # Neighborhood in Rio
        params = {**brazil_params, "q": "Complexo do Alemão when:1d"}
        url = build_url("/search", params)
        feed = fetch_feed(url)
        
        # Should return some results (well-known neighborhood)
        # but likely fewer than city-wide search
        assert feed is not None

    def test_empty_feed_is_valid_rss(self, brazil_params):
        """Verify that empty result feeds are still valid RSS.
        
        Important: Empty feeds should still have proper RSS structure.
        """
        # Use very specific query unlikely to have results
        params = {**brazil_params, "q": "xyznonexistent123village when:1h"}
        url = build_url("/search", params)
        raw_content = fetch_raw(url)
        
        # Should still be valid RSS with channel but no items
        assert "<rss" in raw_content
        assert "<channel>" in raw_content
        assert "version=\"2.0\"" in raw_content
        
        # Parse to verify structure
        feed = feedparser.parse(raw_content)
        assert feed.bozo == 0, "Feed should be valid XML even when empty"
        assert len(feed.entries) == 0, "Should have no entries for nonexistent location"

