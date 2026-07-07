"""Tests for duplicate google_news_id handling during city ingest."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.services.ingestion import ingest_city


def _entry(*, entry_id: str, link: str, title: str = "Headline - Publisher"):
    return {
        "id": entry_id,
        "link": link,
        "title": title,
        "source": {"href": "https://publisher.example"},
        "published_parsed": (2026, 7, 7, 12, 0, 0),
    }


@pytest.mark.asyncio
async def test_ingest_city_skips_existing_google_news_id(async_session):
    existing = SourceGoogleNews(
        google_news_id="dup-id",
        google_news_url="https://news.google.com/existing",
        headline="Existing",
        status=SourceStatus.ready_for_classification,
        fetched_at=datetime.utcnow(),
    )
    async_session.add(existing)
    await async_session.commit()

    class _SessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return async_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    entries = [_entry(entry_id="dup-id", link="https://news.google.com/new")]

    with (
        patch("app.services.ingestion.async_session_maker", _SessionMaker()),
        patch(
            "app.services.ingestion.get_queries_for_city",
            new_callable=AsyncMock,
            return_value=["query"],
        ),
        patch(
            "app.services.ingestion.rate_limited_fetch",
            new_callable=AsyncMock,
            return_value=entries,
        ),
        patch("app.services.ingestion.update_city_stats", new_callable=AsyncMock),
        patch(
            "app.services.ingestion.resolve_google_news_url",
            return_value="https://article.example/1",
        ),
    ):
        new_sources, total = await ingest_city("Test City", when="1h", resolve_urls=True)

    assert total == 1
    assert new_sources == []

    rows = (
        await async_session.exec(select(SourceGoogleNews))
    ).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_ingest_city_continues_after_integrity_error_on_flush(async_session):
    class _SessionMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return async_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    entries = [
        _entry(entry_id="race-id", link="https://news.google.com/race"),
        _entry(entry_id="ok-id", link="https://news.google.com/ok"),
    ]

    real_flush = async_session.flush
    flush_calls = {"count": 0}

    async def flush_with_race(*args, **kwargs):
        flush_calls["count"] += 1
        if flush_calls["count"] == 1:
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("duplicate", params=None, orig=Exception("dup"))
        return await real_flush(*args, **kwargs)

    with (
        patch("app.services.ingestion.async_session_maker", _SessionMaker()),
        patch(
            "app.services.ingestion.get_queries_for_city",
            new_callable=AsyncMock,
            return_value=["query"],
        ),
        patch(
            "app.services.ingestion.rate_limited_fetch",
            new_callable=AsyncMock,
            return_value=entries,
        ),
        patch("app.services.ingestion.update_city_stats", new_callable=AsyncMock),
        patch(
            "app.services.ingestion.resolve_google_news_url",
            side_effect=[
                "https://article.example/race",
                "https://article.example/ok",
            ],
        ),
        patch.object(async_session, "flush", side_effect=flush_with_race),
    ):
        new_sources, _total = await ingest_city("Test City", when="1h", resolve_urls=True)

    assert len(new_sources) == 1
    assert new_sources[0].google_news_id == "ok-id"
