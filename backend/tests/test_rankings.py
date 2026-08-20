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
        
        # Check totals
        assert data["total_victims"] == 4
        assert data["total_events"] == 3
        
        # Check cities ranking
        assert len(data["cities"]) == 2
        rio = next(c for c in data["cities"] if c["city"] == "Rio de Janeiro")
        assert rio["victim_count"] == 3
        assert rio["event_count"] == 2
        assert rio["victim_share"] > 0
        
        # Check states ranking
        assert len(data["states"]) == 2
        rj = next(s for s in data["states"] if s["state"] == "RJ")
        assert rj["victim_count"] == 3
        assert rj["event_count"] == 2
        
        # Check types ranking
        assert len(data["homicide_types"]) == 2
        simples = next(t for t in data["homicide_types"] if t["type"] == "Homicídio simples")
        assert simples["victim_count"] == 3
        assert simples["event_count"] == 2
        
        # Check methods ranking
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
async def test_rankings_rate_per_100k_matched_br(app, async_session, population_fixture):
    """Test that matched BR cities include rate_per_100k and population."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events in matched BR cities
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="São Paulo",
            state="SP",
            victim_count=100
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Brasil",
            city="Rio de Janeiro",
            state="RJ",
            victim_count=50
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
        
        # Check that population_vintage is included
        assert "population_vintage" in data
        assert data["population_vintage"] == 2022
        
        # Check São Paulo has rate and population
        sp = next(c for c in data["cities"] if c["city"] == "São Paulo")
        assert "population" in sp
        assert "rate_per_100k" in sp
        assert sp["population"] == 11451245
        # rate = 100 / 11451245 * 100000 ≈ 0.87
        assert sp["rate_per_100k"] is not None
        assert 0.8 < sp["rate_per_100k"] < 0.9
        
        # Check Rio has rate and population
        rio = next(c for c in data["cities"] if c["city"] == "Rio de Janeiro")
        assert "population" in rio
        assert "rate_per_100k" in rio
        assert rio["population"] == 6211423
        # rate = 50 / 6211423 * 100000 ≈ 0.80
        assert rio["rate_per_100k"] is not None
        assert 0.7 < rio["rate_per_100k"] < 0.9


@pytest.mark.asyncio
async def test_rankings_rate_per_100k_sao_paulo_specific(app, async_session, population_fixture):
    """Test São Paulo (code_muni 3550308) gets correct rate calculation."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create event with known victim count
    event = create_ranking_event(
        event_date=current_start + timedelta(days=1),
        country="Brasil",
        city="São Paulo",
        state="SP",
        victim_count=1000
    )
    
    async_session.add(event)
    await async_session.commit()
    
    from app.database import get_session
    app.dependency_overrides[get_session] = lambda: async_session
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        sp = data["cities"][0]
        assert sp["city"] == "São Paulo"
        assert sp["population"] == 11451245
        # rate = 1000 / 11451245 * 100000 = 8.733...
        expected_rate = 1000 / 11451245 * 100000
        assert sp["rate_per_100k"] is not None
        assert abs(sp["rate_per_100k"] - expected_rate) < 0.01


@pytest.mark.asyncio
async def test_rankings_junk_city_no_rate(app, async_session, population_fixture):
    """Test that junk string 'Joanesburgo' does not get a rate."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create event with junk city name
    event = create_ranking_event(
        event_date=current_start + timedelta(days=1),
        country="Brasil",
        city="Joanesburgo",  # Not a BR city
        state="XX",
        victim_count=10
    )
    
    async_session.add(event)
    await async_session.commit()
    
    from app.database import get_session
    app.dependency_overrides[get_session] = lambda: async_session
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        joanesburg = data["cities"][0]
        assert joanesburg["city"] == "Joanesburgo"
        assert joanesburg["victim_count"] == 10
        # Should not have rate or population
        assert joanesburg.get("rate_per_100k") is None
        assert joanesburg.get("population") is None


@pytest.mark.asyncio
async def test_rankings_chile_no_rate(app, async_session, population_fixture):
    """Test that Chile events do not get rate_per_100k (not using geobr)."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create Chile event
    event = create_ranking_event(
        event_date=current_start + timedelta(days=1),
        country="Chile",
        city="Santiago",
        state="Metropolitana",
        victim_count=20
    )
    
    async_session.add(event)
    await async_session.commit()
    
    from app.database import get_session
    app.dependency_overrides[get_session] = lambda: async_session
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30&country=CL")
        assert response.status_code == 200
        data = response.json()
        
        santiago = data["cities"][0]
        assert santiago["city"] == "Santiago"
        assert santiago["victim_count"] == 20
        # Chile should not have rate or population (INE later, not geobr)
        assert santiago.get("rate_per_100k") is None
        assert santiago.get("population") is None


@pytest.mark.asyncio
async def test_rankings_default_sort_by_rate(app, async_session, population_fixture):
    """Test that rankings default sort by rate_per_100k when available."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events: São Paulo has more victims but lower rate
    # Bauru has fewer victims but higher rate
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="São Paulo",
            state="SP",
            victim_count=100  # rate ≈ 0.87 per 100k
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Brasil",
            city="Bauru",
            state="SP",
            victim_count=10  # rate ≈ 2.64 per 100k (higher!)
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
        
        # Bauru should be first (higher rate despite fewer victims)
        assert data["cities"][0]["city"] == "Bauru"
        assert data["cities"][0]["rate_per_100k"] > data["cities"][1]["rate_per_100k"]
        
        # São Paulo should be second
        assert data["cities"][1]["city"] == "São Paulo"
