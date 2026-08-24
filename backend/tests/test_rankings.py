"""Tests for public stats/rankings endpoint."""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

from app.models.unique_event import UniqueEvent


def create_ranking_event(
    event_date: datetime,
    country: str = "Brasil",
    state: str = "RJ",
    city: str = "Rio de Janeiro",
    homicide_type: str = "Homicídio simples",
    method_of_death: str = "Arma de fogo",
    victim_count: int = 1,
    **kwargs
) -> UniqueEvent:
    """Helper to create test events for rankings."""
    return UniqueEvent(
        title=f"Event in {city}",
        event_date=event_date,
        country=country,
        state=state,
        city=city,
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type=homicide_type,
        method_of_death=method_of_death,
        victim_count=victim_count,
        latitude=Decimal("-22.9068") if country == "Brasil" else Decimal("-33.4489"),
        longitude=Decimal("-43.1729") if country == "Brasil" else Decimal("-70.6693"),
        source_count=1,
        **kwargs
    )


@pytest.mark.asyncio
async def test_rankings_empty_database(client: AsyncClient):
    """Test rankings endpoint with no events."""
    response = await client.get("/api/public/stats/rankings")
    assert response.status_code == 200
    data = response.json()
    
    assert data["total_victims"] == 0
    assert data["total_events"] == 0
    assert data["cities"] == []
    assert data["states"] == []
    assert data["countries"] == []
    assert data["homicide_types"] == []
    assert data["methods"] == []


@pytest.mark.asyncio
async def test_rankings_basic_aggregation(app, async_session):
    """Test basic ranking aggregation by city, state, type, and method."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=365)
    
    # Create events across different dimensions
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            city="Rio de Janeiro",
            state="RJ",
            homicide_type="Homicídio simples",
            method_of_death="Arma de fogo",
            victim_count=2
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            city="Rio de Janeiro",
            state="RJ",
            homicide_type="Latrocínio",
            method_of_death="Arma branca",
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=3),
            city="São Paulo",
            state="SP",
            homicide_type="Homicídio simples",
            method_of_death="Arma de fogo",
            victim_count=1
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=365")
        assert response.status_code == 200
        data = response.json()
        
        # Check aggregated totals
        assert data["total_victims"] == 4
        assert data["total_events"] == 3
        
        # Check cities ranking
        assert len(data["cities"]) == 2
        assert data["cities"][0]["city"] == "Rio de Janeiro"
        assert data["cities"][0]["victim_count"] == 3
        assert data["cities"][0]["event_count"] == 2
        
        # Check states ranking
        assert len(data["states"]) == 2
        rj = next(s for s in data["states"] if s["state"] == "RJ")
        assert rj["victim_count"] == 3
        assert rj["event_count"] == 2
        
        # Check homicide types
        assert len(data["homicide_types"]) == 2
        simples = next(t for t in data["homicide_types"] if t["type"] == "Homicídio simples")
        assert simples["victim_count"] == 3
        assert simples["event_count"] == 2
        
        # Check methods
        assert len(data["methods"]) == 2
        arma_fogo = next(m for m in data["methods"] if m["method"] == "Arma de fogo")
        assert arma_fogo["victim_count"] == 3
        assert arma_fogo["event_count"] == 2


@pytest.mark.asyncio
async def test_rankings_country_filter_brazil(app, async_session):
    """Test country filter for Brazil only."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events in Brazil and Chile
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="Rio de Janeiro",
            state="RJ",
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Chile",
            city="Santiago",
            state="Metropolitana",
            victim_count=1
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Should only include Brazil
        assert data["total_events"] == 1
        assert len(data["cities"]) == 1
        assert data["cities"][0]["city"] == "Rio de Janeiro"
        assert len(data["countries"]) == 1
        assert data["countries"][0]["country"] == "Brasil"


@pytest.mark.asyncio
async def test_rankings_country_filter_chile(app, async_session):
    """Test country filter for Chile only."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events in Chile only
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Chile",
            city="Santiago",
            state="Metropolitana",
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Chile",
            city="Valparaíso",
            state="Valparaíso",
            victim_count=1
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30&country=CL")
        assert response.status_code == 200
        data = response.json()
        
        # Should only include Chile
        assert data["total_events"] == 2
        assert len(data["cities"]) == 2
        assert all(c["city"] in ["Santiago", "Valparaíso"] for c in data["cities"])
        assert len(data["countries"]) == 1
        assert data["countries"][0]["country"] == "Chile"


@pytest.mark.asyncio
async def test_rankings_empty_chile_data(app, async_session):
    """Test that empty Chile data doesn't break the page."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events only in Brazil
    event = create_ranking_event(
        event_date=current_start + timedelta(days=1),
        country="Brasil",
        city="Rio de Janeiro",
        state="RJ",
        victim_count=1
    )
    
    async_session.add(event)
    await async_session.commit()
    
    from app.database import get_session
    app.dependency_overrides[get_session] = lambda: async_session
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Request without country filter (should include both)
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200
        data = response.json()
        
        # Chile should be absent or have 0 events
        assert data["total_events"] >= 1
        chile_rows = [c for c in data["countries"] if c["country"] == "Chile"]
        assert len(chile_rows) == 0  # Chile should not appear if no events
        
        # Filter by Chile should return empty
        response = await client.get("/api/public/stats/rankings?days=30&country=CL")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 0
        assert len(data["cities"]) == 0
        assert len(data["states"]) == 0


@pytest.mark.asyncio
async def test_rankings_delta_calculation(app, async_session):
    """Test delta vs previous period calculation."""
    now = datetime.utcnow()
    
    # Previous period (31-60 days ago): 2 victims
    prev_period_start = now - timedelta(days=60)
    prev_period_end = now - timedelta(days=31)
    
    # Current period (last 30 days): 5 victims
    current_period_start = now - timedelta(days=30)
    
    events = [
        # Previous period events
        create_ranking_event(
            event_date=prev_period_start + timedelta(days=1),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=1
        ),
        create_ranking_event(
            event_date=prev_period_start + timedelta(days=2),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=1
        ),
        # Current period events
        create_ranking_event(
            event_date=current_period_start + timedelta(days=1),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=2
        ),
        create_ranking_event(
            event_date=current_period_start + timedelta(days=2),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=3
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200
        data = response.json()
        
        # Current period should have 5 victims
        assert data["total_victims"] == 5
        assert data["total_events"] == 2
        
        # Rio should show delta of +3 victims (+2 events)
        rio = data["cities"][0]
        assert rio["city"] == "Rio de Janeiro"
        assert rio["victim_count"] == 5
        assert rio["event_count"] == 2
        assert rio["victim_delta"] == 3  # 5 current - 2 previous
        assert rio["event_delta"] == 0  # 2 current - 2 previous


@pytest.mark.asyncio
async def test_rankings_different_periods(app, async_session):
    """Test rankings with different time periods (7, 30, 365 days)."""
    now = datetime.utcnow()
    
    # Create events at different times
    events = [
        # Last 7 days
        create_ranking_event(event_date=now - timedelta(days=3), victim_count=1),
        # Last 30 days (but not 7)
        create_ranking_event(event_date=now - timedelta(days=15), victim_count=1),
        # Last 365 days (but not 30)
        create_ranking_event(event_date=now - timedelta(days=180), victim_count=1),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Test 7 days
        response = await client.get("/api/public/stats/rankings?days=7")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 1
        assert data["period_days"] == 7
        
        # Test 30 days
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 2
        assert data["period_days"] == 30
        
        # Test 365 days
        response = await client.get("/api/public/stats/rankings?days=365")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 3
        assert data["period_days"] == 365


@pytest.mark.asyncio
async def test_rankings_victim_vs_event_counts(app, async_session):
    """Test that rankings correctly distinguish victim count from event count."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events with different victim counts
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            city="Rio de Janeiro",
            victim_count=5  # Multi-victim event
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            city="Rio de Janeiro",
            victim_count=1  # Single victim
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=3),
            city="São Paulo",
            victim_count=2
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200
        data = response.json()
        
        # Total: 8 victims, 3 events
        assert data["total_victims"] == 8
        assert data["total_events"] == 3
        
        # Rio: 6 victims, 2 events
        rio = next(c for c in data["cities"] if c["city"] == "Rio de Janeiro")
        assert rio["victim_count"] == 6
        assert rio["event_count"] == 2
        
        # SP: 2 victims, 1 event
        sp = next(c for c in data["cities"] if c["city"] == "São Paulo")
        assert sp["victim_count"] == 2
        assert sp["event_count"] == 1


@pytest.mark.asyncio
async def test_rankings_http_200_with_br_fixture(app, async_session):
    """
    Test that GET /api/public/stats/rankings returns HTTP 200 with BR fixture.
    
    Regression test for issue #161: COUNTRY_NAMES import missing caused HTTP 500.
    """
    now = datetime.utcnow()
    
    br_event = UniqueEvent(
        title="Evento no Brasil",
        event_date=now - timedelta(days=10),
        country="BR",
        state="SP",
        city="São Paulo",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        method_of_death="Arma de fogo",
        victim_count=1,
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        source_count=1,
    )
    
    async_session.add(br_event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["total_events"] >= 1
        assert len(data["countries"]) >= 1
        # Verify BR is normalized to "Brasil" display name
        br_country = next((c for c in data["countries"] if c["country"] == "Brasil"), None)
        assert br_country is not None, "BR should be normalized to 'Brasil' in display"


@pytest.mark.asyncio
async def test_rankings_http_200_with_cl_fixture(app, async_session):
    """
    Test that GET /api/public/stats/rankings returns HTTP 200 with CL fixture.
    
    Regression test for issue #161: COUNTRY_NAMES import missing caused HTTP 500.
    Tests that state=Metropolitana is still counted for CL (issue #157).
    """
    now = datetime.utcnow()
    
    cl_event = UniqueEvent(
        title="Evento en Chile",
        event_date=now - timedelta(days=10),
        country="CL",
        state="Metropolitana",
        city="Santiago",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        method_of_death="Arma de fogo",
        victim_count=1,
        latitude=Decimal("-33.4489"),
        longitude=Decimal("-70.6693"),
        source_count=1,
    )
    
    async_session.add(cl_event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["total_events"] >= 1
        assert len(data["countries"]) >= 1
        # Verify CL is normalized to "Chile" display name
        cl_country = next((c for c in data["countries"] if c["country"] == "Chile"), None)
        assert cl_country is not None, "CL should be normalized to 'Chile' in display"
        # Verify state=Metropolitana is counted
        assert len(data["states"]) >= 1
        metropolitana_state = next((s for s in data["states"] if s["state"] == "Metropolitana"), None)
        assert metropolitana_state is not None, "state=Metropolitana should be counted for CL"


@pytest.mark.asyncio
async def test_rankings_country_filter_iso_codes_issue_152(app, async_session):
    """
    Test rankings country filter with ISO codes (issue #152).
    
    - BR default (omit country field) should store as "BR"
    - CL should match only CL events
    - BR filter should include both new "BR" and legacy "Brasil" events
    """
    now = datetime.utcnow()
    
    # Create BR event with new default (omit country, should default to "BR")
    br_event_new = UniqueEvent(
        title="Evento no Brasil (novo default)",
        event_date=now - timedelta(days=10),
        # country omitted - should default to "BR"
        state="SP",
        city="São Paulo",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        method_of_death="Arma de fogo",
        victim_count=2,
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        source_count=1,
    )
    
    # Create legacy Brasil event (explicit "Brasil")
    br_event_legacy = UniqueEvent(
        title="Evento no Brasil (legado)",
        event_date=now - timedelta(days=15),
        country="Brasil",  # Legacy value
        state="RJ",
        city="Rio de Janeiro",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        method_of_death="Arma de fogo",
        victim_count=3,
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
        source_count=1,
    )
    
    # Create CL event (explicit "CL")
    cl_event = UniqueEvent(
        title="Evento en Chile",
        event_date=now - timedelta(days=12),
        country="CL",
        state="RM",
        city="Santiago",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        method_of_death="Arma de fogo",
        victim_count=1,
        latitude=Decimal("-33.4489"),
        longitude=Decimal("-70.6693"),
        source_count=1,
    )
    
    async_session.add_all([br_event_new, br_event_legacy, cl_event])
    await async_session.commit()
    await async_session.refresh(br_event_new)
    
    # Verify BR event defaulted to "BR" (not "Brasil")
    assert br_event_new.country == "BR", f"Expected 'BR', got '{br_event_new.country}'"
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Test 1: Filter by CL should return only CL event
        response_cl = await client.get("/api/public/stats/rankings?days=30&country=CL")
        assert response_cl.status_code == 200
        data_cl = response_cl.json()
        
        # Should count only CL event (1 victim)
        assert data_cl["total_victims"] == 1, f"CL filter should count only CL event, got {data_cl['total_victims']} victims"
        assert data_cl["total_events"] == 1, f"CL filter should count only CL event, got {data_cl['total_events']} events"
        
        # Cities should only include Santiago
        assert len(data_cl["cities"]) == 1
        assert data_cl["cities"][0]["city"] == "Santiago"
        
        # Test 2: Filter by BR should include both new BR and legacy "Brasil" events
        response_br = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response_br.status_code == 200
        data_br = response_br.json()
        
        # Should count both BR events (2 + 3 = 5 victims)
        assert data_br["total_victims"] == 5, f"BR filter should count both BR and legacy Brasil events, got {data_br['total_victims']} victims"
        assert data_br["total_events"] == 2, f"BR filter should count both BR and legacy Brasil events, got {data_br['total_events']} events"
        
        # Cities should include both São Paulo and Rio de Janeiro
        assert len(data_br["cities"]) == 2
        city_names = {city["city"] for city in data_br["cities"]}
        assert city_names == {"São Paulo", "Rio de Janeiro"}
        
        # Test 3: No country filter should include all events
        response_all = await client.get("/api/public/stats/rankings?days=30")
        assert response_all.status_code == 200
        data_all = response_all.json()
        
        # Should count all events (2 + 3 + 1 = 6 victims)
        assert data_all["total_victims"] == 6
        assert data_all["total_events"] == 3
