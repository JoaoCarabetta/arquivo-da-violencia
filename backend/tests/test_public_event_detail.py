"""Tests for GET /api/public/events/{id} detail payload."""

from datetime import datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.models.unique_event import UniqueEvent


def _base_event(**kwargs) -> UniqueEvent:
    defaults = dict(
        title="Homicídio em Curitiba",
        event_date=datetime(2026, 4, 20, 12, 0, 0),
        state="PR",
        city="Curitiba",
        country="Brasil",
        street="Rua das Flores",
        neighborhood="Centro",
        latitude=Decimal("-25.4293"),
        longitude=Decimal("-49.314262"),
        location_precision="approximate",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        victim_count=2,
        perpetrator_count=1,
        source_count=1,
        confirmed=True,
        merged_data={"internal": True},
        place_id="secret-place",
    )
    defaults.update(kwargs)
    return UniqueEvent(**defaults)


@pytest.mark.asyncio
async def test_public_event_detail_includes_dictionary_fields(
    app, async_session, client: AsyncClient
):
    event = _base_event()
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)

    response = await client.get(f"/api/public/events/{event.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["country"] == "Brasil"
    assert data["street"] == "Rua das Flores"
    assert data["location_precision"] == "approximate"
    assert data["perpetrator_count"] == 1
    assert data["updated_at"] is not None
    assert "merged_data" not in data
    assert "confirmed" not in data
    assert "place_id" not in data


@pytest.mark.asyncio
async def test_public_event_detail_returns_linked_source(
    app, async_session, client: AsyncClient
):
    event = _base_event(source_count=1)
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    event_id = event.id
    event_title = event.title
    event_date = event.event_date
    event_city = event.city
    event_state = event.state

    source = SourceGoogleNews(
        google_news_id="detail-test-source",
        google_news_url="https://news.google.com/rss/articles/abc",
        resolved_url="https://g1.globo.com/pr/parana/noticia/teste",
        headline="Homem morre após briga em Curitiba",
        publisher_name="G1",
        published_at=datetime(2026, 4, 19, 8, 0, 0),
        status=SourceStatus.extracted,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

    async_session.add(
        RawEvent(
            title=event_title,
            event_date=event_date,
            city=event_city,
            state=event_state,
            source_google_news_id=source.id,
            unique_event_id=event_id,
            deduplication_status="matched",
        )
    )
    await async_session.commit()

    response = await client.get(f"/api/public/events/{event_id}")

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["kind"] == "source"
    assert sources[0]["url"] == "https://g1.globo.com/pr/parana/noticia/teste"
    assert sources[0]["google_news_url"] == "https://news.google.com/rss/articles/abc"
    assert sources[0]["headline"] == "Homem morre após briga em Curitiba"


@pytest.mark.asyncio
async def test_public_event_detail_returns_raw_fallback_without_source_link(
    app, async_session, client: AsyncClient
):
    event = _base_event(
        title="Evento sem fonte vinculada",
        source_count=1,
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    event_id = event.id
    event_city = event.city
    event_state = event.state

    async_session.add(
        RawEvent(
            title="Matéria extraída sem source_google_news",
            event_date=datetime(2026, 4, 18, 9, 0, 0),
            city=event_city,
            state=event_state,
            source_google_news_id=None,
            unique_event_id=event_id,
            deduplication_status="matched",
        )
    )
    await async_session.commit()

    response = await client.get(f"/api/public/events/{event_id}")

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["kind"] == "raw_fallback"
    assert sources[0]["url"] is None
    assert sources[0]["headline"] == "Matéria extraída sem source_google_news"


@pytest.mark.asyncio
async def test_public_event_detail_not_found(client: AsyncClient):
    response = await client.get("/api/public/events/999999")
    assert response.status_code == 404
