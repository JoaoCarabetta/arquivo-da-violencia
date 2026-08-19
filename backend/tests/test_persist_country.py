"""Tests for persisting country from ingest to UniqueEvent."""

import pytest
from datetime import datetime
from decimal import Decimal

from app.models.unique_event import UniqueEvent
from app.models.raw_event import RawEvent
from app.models.source_google_news import SourceGoogleNews, SourceStatus
from app.services.enrichment import create_unique_event_from_cluster


@pytest.mark.asyncio
async def test_chilean_fixture_stores_country_cl(async_session):
    """Test 1: UniqueEvent persistence - Chilean fixture stores country CL (not Brasil)."""
    # Create a Chilean SourceGoogleNews
    source = SourceGoogleNews(
        google_news_id="test_cl_001",
        google_news_url="https://news.google.com/test_cl",
        headline="Homicidio en Santiago",
        publisher_name="Test CL Publisher",
        search_query="homicidio Santiago",
        status=SourceStatus.extracted,
        country="CL",
    )
    async_session.add(source)
    await async_session.commit()
    await async_session.refresh(source)
    
    # Create a RawEvent from Chilean source
    raw_event = RawEvent(
        source_google_news_id=source.id,
        event_family="homicidio",
        event_subtype="simples",
        event_date=datetime(2026, 8, 15, 14, 30),
        city="Santiago",
        state="Metropolitana",
        title="Homicidio en Santiago centro",
        chronological_description="Una persona murió",
        victim_count=1,
        extraction_data={
            "location_info": {
                "city": "Santiago",
                "region": "Metropolitana",
                "country": "CL",
            }
        },
        country="CL",
    )
    async_session.add(raw_event)
    await async_session.commit()
    await async_session.refresh(raw_event)
    
    # Create UniqueEvent from cluster
    unique_event = await create_unique_event_from_cluster([raw_event])
    
    # Refresh to get the persisted state
    await async_session.refresh(unique_event)
    
    # Assert: country should be CL, not "Brasil"
    assert unique_event.country == "CL", f"Expected country='CL', got '{unique_event.country}'"
    assert unique_event.country != "Brasil", "Country should not be hardcoded to Brasil"
    assert unique_event.city == "Santiago"
    assert unique_event.state == "Metropolitana"


@pytest.mark.asyncio
async def test_rankings_country_breakdown_with_cl_and_legacy_brasil(app, async_session):
    """Test 2: Public rankings country breakdown - CL row appears, Brasil treated as BR."""
    from datetime import timedelta
    from httpx import AsyncClient
    from app.database import get_session
    
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events with different country values:
    # - New CL event with canonical code
    # - Legacy Brasil event (should be treated as BR)
    # - New BR event with canonical code
    events = [
        UniqueEvent(
            title="Chilean event",
            event_date=current_start + timedelta(days=1),
            country="CL",  # Canonical code
            state="Metropolitana",
            city="Santiago",
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            victim_count=1,
            latitude=Decimal("-33.4489"),
            longitude=Decimal("-70.6693"),
            source_count=1,
        ),
        UniqueEvent(
            title="Legacy Brasil event",
            event_date=current_start + timedelta(days=2),
            country="Brasil",  # Legacy display name (should be treated as BR)
            state="RJ",
            city="Rio de Janeiro",
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            victim_count=1,
            latitude=Decimal("-22.9068"),
            longitude=Decimal("-43.1729"),
            source_count=1,
        ),
        UniqueEvent(
            title="New BR event",
            event_date=current_start + timedelta(days=3),
            country="BR",  # Canonical code
            state="SP",
            city="São Paulo",
            event_family="homicidio",
            event_subtype="simples",
            content_class="incident",
            victim_count=1,
            latitude=Decimal("-23.5505"),
            longitude=Decimal("-46.6333"),
            source_count=1,
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    app.dependency_overrides[get_session] = lambda: async_session
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200
        data = response.json()
        
        # Total should include all 3 events
        assert data["total_events"] == 3
        assert data["total_victims"] == 3
        
        # Countries breakdown
        countries = data["countries"]
        assert len(countries) == 2, f"Expected 2 countries (BR and CL), got {len(countries)}: {countries}"
        
        # Find BR and CL in results
        country_map = {c["country"]: c for c in countries}
        
        # CL should appear with display name "Chile"
        assert "Chile" in country_map, f"Chile not found in countries: {list(country_map.keys())}"
        chile = country_map["Chile"]
        assert chile["victim_count"] == 1
        assert chile["event_count"] == 1
        
        # BR should appear with display name "Brasil" and count BOTH legacy "Brasil" and new "BR" events
        assert "Brasil" in country_map, f"Brasil not found in countries: {list(country_map.keys())}"
        brasil = country_map["Brasil"]
        assert brasil["victim_count"] == 2, f"Expected 2 victims for Brasil (legacy + new), got {brasil['victim_count']}"
        assert brasil["event_count"] == 2, f"Expected 2 events for Brasil (legacy + new), got {brasil['event_count']}"
        
        # Test country filter: ?country=CL should show only Chilean event
        response_cl = await client.get("/api/public/stats/rankings?days=30&country=CL")
        assert response_cl.status_code == 200
        data_cl = response_cl.json()
        assert data_cl["total_events"] == 1
        assert len(data_cl["cities"]) == 1
        assert data_cl["cities"][0]["city"] == "Santiago"
        
        # Test country filter: ?country=BR should show both legacy and new BR events
        response_br = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response_br.status_code == 200
        data_br = response_br.json()
        assert data_br["total_events"] == 2, f"Expected 2 events for BR filter, got {data_br['total_events']}"
        assert len(data_br["cities"]) == 2
        city_names = {c["city"] for c in data_br["cities"]}
        assert "Rio de Janeiro" in city_names
        assert "São Paulo" in city_names
