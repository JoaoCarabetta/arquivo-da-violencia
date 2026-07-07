"""Tests for the public single-event detail endpoint."""

from datetime import datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.models.unique_event import UniqueEvent


@pytest.mark.asyncio
async def test_public_event_detail_includes_sources_and_dictionary_fields(
    app, async_session, client: AsyncClient
):
    source = SourceGoogleNews(
        google_news_id="gn-detail-1",
        google_news_url="https://news.google.com/articles/detail-1",
        resolved_url="https://example.com/story-1",
        headline="Homicídio em teste",
        publisher_name="Folha de Teste",
        published_at=datetime(2025, 6, 1, 12, 0, 0),
        status=SourceStatus.extracted,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

    event = UniqueEvent(
        title="Evento público de teste",
        event_date=datetime(2025, 6, 1, 8, 0, 0),
        time_of_day="manhã",
        country="Brasil",
        state="RJ",
        city="Rio de Janeiro",
        neighborhood="Centro",
        street="Rua A, 10",
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
        location_precision="neighborhood_center",
        event_family="homicidio",
        event_subtype="simples",
        method_of_death="arma de fogo",
        victim_count=1,
        perpetrator_count=2,
        victims_summary="1 vítima identificada",
        security_force_involved=False,
        chronological_description="Descrição cronológica de teste.",
        formatted_address="Centro, Rio de Janeiro — RJ",
        source_count=1,
        merged_data={"internal": True},
        place_id="secret-place-id",
        confirmed=True,
        needs_enrichment=True,
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)

    raw_event = RawEvent(
        source_google_news_id=source.id,
        unique_event_id=event.id,
        title="Evento público de teste",
        deduplication_status="matched",
    )
    async_session.add(raw_event)
    await async_session.commit()

    response = await client.get(f"/api/public/events/{event.id}")
    assert response.status_code == 200
    payload = response.json()

    assert payload["country"] == "Brasil"
    assert payload["street"] == "Rua A, 10"
    assert payload["location_precision"] == "neighborhood_center"
    assert payload["perpetrator_count"] == 2
    assert payload["victims_summary"] == "1 vítima identificada"
    assert payload["formatted_address"] == "Centro, Rio de Janeiro — RJ"
    assert payload["updated_at"] is not None
    assert "merged_data" not in payload
    assert "place_id" not in payload
    assert "confirmed" not in payload

    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["url"] == "https://example.com/story-1"
    assert payload["sources"][0]["headline"] == "Homicídio em teste"


@pytest.mark.asyncio
async def test_public_event_detail_falls_back_to_google_news_url(
    app, async_session, client: AsyncClient
):
    source = SourceGoogleNews(
        google_news_id="gn-detail-2",
        google_news_url="https://news.google.com/articles/detail-2",
        resolved_url=None,
        headline="Sem URL resolvida",
        publisher_name="Portal",
        status=SourceStatus.extracted,
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)

    event = UniqueEvent(
        title="Evento com fallback",
        event_date=datetime.utcnow(),
        state="SP",
        city="São Paulo",
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        source_count=1,
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)

    async_session.add(
        RawEvent(
            source_google_news_id=source.id,
            unique_event_id=event.id,
            deduplication_status="matched",
        )
    )
    await async_session.commit()

    response = await client.get(f"/api/public/events/{event.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["url"] == "https://news.google.com/articles/detail-2"
