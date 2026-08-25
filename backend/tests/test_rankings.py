"""Tests for public stats/rankings endpoint."""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

from app.models.unique_event import UniqueEvent
from app.geography import BRAZILIAN_STATES


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
async def test_rankings_chile_includes_metropolitana_region(app, async_session):
    """Test that Chilean events with Chilean region names (e.g. Metropolitana) are included (issue #157)."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create Chilean event with Metropolitana region (was previously excluded due to BR UF filter)
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="CL",
            city="Conchalí",
            state="Metropolitana",  # Chilean region name
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="CL",
            city="La Serena",
            state="Coquimbo",  # Another Chilean region
            victim_count=2
        ),
    ]
    
    for event in events:
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
        
        # Both Chilean events should be included
        assert data["total_events"] == 2
        assert data["total_victims"] == 3
        assert len(data["cities"]) == 2
        
        # Check that Metropolitana region events are counted
        cities = {c["city"]: c for c in data["cities"]}
        assert "Conchalí" in cities
        assert cities["Conchalí"]["victim_count"] == 1
        assert "La Serena" in cities
        assert cities["La Serena"]["victim_count"] == 2


@pytest.mark.asyncio
async def test_rankings_brazil_excludes_non_uf_states(app, async_session):
    """Test that Brazilian events with non-UF states (e.g. Chilean regions) are excluded."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create Brazilian events: one with valid UF, one with invalid state
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="São Paulo",
            state="SP",  # Valid BR UF
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Brasil",
            city="Rio de Janeiro",
            state="Metropolitana",  # Invalid for Brazil (Chilean region)
            victim_count=1
        ),
    ]
    
    for event in events:
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
        
        # Should only include the valid UF event
        assert data["total_events"] == 1
        assert data["total_victims"] == 1
        assert len(data["cities"]) == 1
        assert data["cities"][0]["city"] == "São Paulo"


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


@pytest.mark.asyncio
async def test_rankings_campinas_not_hardcoded(app, async_session, population_fixture):
    """Test that Campinas gets a rate even though it's not in any hardcoded list.
    
    This proves the lookup uses the database, not a hardcoded mapping.
    Campinas (code_muni 3509502) is in the fixture but was never mentioned in code.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create event in Campinas - NOT in any hardcoded list
    event = create_ranking_event(
        event_date=current_start + timedelta(days=1),
        country="Brasil",
        city="Campinas",
        state="SP",
        victim_count=25
    )
    
    async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        campinas = data["cities"][0]
        assert campinas["city"] == "Campinas"
        assert campinas["victim_count"] == 25
        # Should have rate and population despite not being hardcoded
        assert campinas["rate_per_100k"] is not None
        assert campinas["population"] == 1213792  # From fixture
        # rate = 25 / 1213792 * 100000 ≈ 2.06
        expected_rate = 25 / 1213792 * 100000
        assert abs(campinas["rate_per_100k"] - expected_rate) < 0.01


@pytest.mark.asyncio
async def test_rankings_country_rate_brasil(app, async_session, population_fixture):
    """Test that Brasil country row includes rate_per_100k and population from cached IBGE data.
    
    Brasil national population = sum of all state populations = sum of all municipalities.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events in Brazil
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="São Paulo",
            state="SP",
            victim_count=50
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Brasil",
            city="Rio de Janeiro",
            state="RJ",
            victim_count=30
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
        
        # Should have a Brasil/BR country row
        assert len(data["countries"]) == 1
        brasil = data["countries"][0]
        assert brasil["country"] == "Brasil"
        assert brasil["victim_count"] == 80
        
        # Should have rate and population from cached IBGE data
        # Fixture has: São Paulo (11451245) + Rio (6211423) + Bauru (379297) + Campinas (1213792) = 19255757
        assert brasil["population"] is not None
        assert brasil["population"] == 19255757
        assert brasil["rate_per_100k"] is not None
        expected_rate = 80 / 19255757 * 100000
        assert abs(brasil["rate_per_100k"] - expected_rate) < 0.01


@pytest.mark.asyncio
async def test_rankings_country_rate_chile(app, async_session, population_fixture):
    """Test that Chile country row has null rate and population (no Brazilian denominator)."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create events in Chile
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="CL",
            city="Santiago",
            state="Región Metropolitana",
            victim_count=25
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
        
        # Should have a Chile country row
        chile = next((c for c in data["countries"] if c["country"] == "Chile"), None)
        assert chile is not None
        assert chile["victim_count"] == 25
        
        # Chile should have null rate and population
        assert chile["rate_per_100k"] is None
        assert chile["population"] is None


@pytest.mark.asyncio
async def test_rankings_city_includes_state_abbrev(app, async_session, population_fixture):
    """Test that city rows include state_abbrev for matched BR cities.
    
    A city with a known IBGE match includes state_abbrev of length 2.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create event in a known city
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="São Paulo",
            state="SP",
            victim_count=10
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
        
        # São Paulo should have state_abbrev
        sao_paulo = data["cities"][0]
        assert sao_paulo["city"] == "São Paulo"
        assert "state_abbrev" in sao_paulo
        assert sao_paulo["state_abbrev"] == "SP"
        assert len(sao_paulo["state_abbrev"]) == 2
        
        # Should also have state display name
        assert "state" in sao_paulo
        assert sao_paulo["state"] == "SP"


@pytest.mark.asyncio
async def test_rankings_city_duplicate_names_different_uf(app, async_session, population_fixture):
    """Test that two same-named cities in different UFs are distinct rows with different abbrev.
    
    Example: Lajeado exists in RS and TO. They should be separate rows.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create two cities with the same name in different states
    # We'll use the fixture cities and create hypothetical duplicates
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="TestCity",
            state="SP",
            victim_count=10
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="Brasil",
            city="TestCity",
            state="RJ",
            victim_count=5
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
        
        # Should have 2 separate TestCity rows
        test_cities = [c for c in data["cities"] if c["city"] == "TestCity"]
        assert len(test_cities) == 2
        
        # Should have different state_abbrev
        abbrevs = [c["state_abbrev"] for c in test_cities]
        assert "SP" in abbrevs
        assert "RJ" in abbrevs
        assert len(set(abbrevs)) == 2  # Both distinct


@pytest.mark.asyncio
async def test_rankings_city_unmatched_no_invented_uf(app, async_session, population_fixture):
    """Test that unmatched junk cities do not invent a UF.
    
    Joanesburgo (South Africa) should not get a Brazilian UF.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create event in a non-existent/foreign city
    events = [
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="Brasil",
            city="Joanesburgo",
            state="ZA",  # Not a Brazilian state
            victim_count=10
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
        
        # Joanesburgo should be in the list
        joanesburgo = next((c for c in data["cities"] if c["city"] == "Joanesburgo"), None)
        assert joanesburgo is not None
        
        # Should NOT have a state_abbrev (ZA is not a valid Brazilian UF)
        assert joanesburgo.get("state_abbrev") is None
        
        # Should still have state display name from event
        assert joanesburgo.get("state") == "ZA"


@pytest.mark.asyncio
async def test_rankings_city_limit_default(app, async_session, population_fixture):
    """Test that rankings default to returning top 50 cities for fast load."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=30)
    
    # Create 100 cities to test limiting
    events = []
    for i in range(100):
        events.append(
            create_ranking_event(
                event_date=current_start + timedelta(days=1),
                country="Brasil",
                city=f"City{i:03d}",
                state="SP",
                victim_count=1
            )
        )
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        # Default request should limit to 50 cities
        response = await client.get("/api/public/stats/rankings?days=30&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Should return exactly 50 cities (default limit)
        assert len(data["cities"]) == 50
        
        # Request with explicit limit=100
        response_all = await client.get("/api/public/stats/rankings?days=30&country=BR&city_limit=100")
        assert response_all.status_code == 200
        data_all = response_all.json()
        
        # Should return all 100 cities
        assert len(data_all["cities"]) == 100
        
        # Request with limit=10
        response_small = await client.get("/api/public/stats/rankings?days=30&country=BR&city_limit=10")
        assert response_small.status_code == 200
        data_small = response_small.json()
        
        # Should return only 10 cities
        assert len(data_small["cities"]) == 10


# ============================================================================
# Matrix endpoint tests (Issue #141)
# ============================================================================

def test_matrix_months_pure_logic():
    """Test matrix_months helper with frozen time (pure unit test, no HTTP/FastAPI).
    
    This is the clock/fixture test: verifies that after a new month starts,
    the next column appears without schema changes.
    """
    from datetime import timezone
    from app.routers.public import matrix_months
    
    # Test 1: September 2026 (UTC-4) → includes Jul, Aug, Sep
    sept_now = datetime(2026, 9, 15, tzinfo=timezone(timedelta(hours=-4)))
    result_sept = matrix_months(sept_now)
    assert result_sept == ["2026-07", "2026-08", "2026-09"]
    assert result_sept[0] == "2026-07", "First month always July 2026"
    
    # Test 2: August 2026 (UTC-4) → includes Jul, Aug only
    aug_now = datetime(2026, 8, 19, tzinfo=timezone(timedelta(hours=-4)))
    result_aug = matrix_months(aug_now)
    assert result_aug == ["2026-07", "2026-08"]
    assert "2026-09" not in result_aug, "September should not appear in August"
    
    # Test 3: July 2026 (UTC-4) → includes Jul only
    july_now = datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=-4)))
    result_july = matrix_months(july_now)
    assert result_july == ["2026-07"]
    
    # Test 4: December 2026 (UTC-4) → crosses year boundary correctly
    dec_now = datetime(2026, 12, 31, tzinfo=timezone(timedelta(hours=-4)))
    result_dec = matrix_months(dec_now)
    assert result_dec[0] == "2026-07"
    assert result_dec[-1] == "2026-12"
    assert len(result_dec) == 6  # Jul through Dec


@pytest.mark.asyncio
async def test_matrix_months_start_july_2026(app, async_session, population_fixture):
    """Test matrix endpoint returns months starting with 2026-07 as first column."""
    now = datetime.utcnow()
    
    # Create events in July and August 2026
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",
            country="Brasil",
            victim_count=1
        ),
        create_ranking_event(
            event_date=datetime(2026, 8, 10),
            state="RJ",
            country="Brasil",
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
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # Months should start with "2026-07" and include "2026-08"
        assert "months" in data
        assert len(data["months"]) >= 2
        assert data["months"][0] == "2026-07"
        assert "2026-08" in data["months"]


@pytest.mark.asyncio
async def test_matrix_uf_with_population_has_rate(app, async_session, population_fixture):
    """Test UF with population has numeric rate_per_100k; unmatched state excluded."""
    # Create events in known UFs
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",  # Known state with population
            country="Brasil",
            victim_count=5
        ),
        create_ranking_event(
            event_date=datetime(2026, 7, 16),
            state="RJ",  # Another known state
            country="Brasil",
            victim_count=3
        ),
        create_ranking_event(
            event_date=datetime(2026, 7, 17),
            state=None,  # Unmatched state should be excluded
            country="Brasil",
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
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # UFs should have population and rate_per_100k
        assert "ufs" in data
        
        # Find SP and RJ in the results
        sp_uf = next((uf for uf in data["ufs"] if uf["abbrev"] == "SP"), None)
        rj_uf = next((uf for uf in data["ufs"] if uf["abbrev"] == "RJ"), None)
        
        assert sp_uf is not None
        assert rj_uf is not None
        
        # Check population exists
        assert sp_uf["population"] > 0
        assert rj_uf["population"] > 0
        
        # Check cells have rate_per_100k
        july_cell = next((c for c in sp_uf["cells"] if c["month"] == "2026-07"), None)
        assert july_cell is not None
        assert "rate_per_100k" in july_cell
        assert july_cell["rate_per_100k"] > 0
        assert july_cell["victims"] == 5


@pytest.mark.asyncio
async def test_matrix_type_rows_victim_sums(app, async_session, population_fixture):
    """Test type-row victim sums vs monthly victim totals for included types."""
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",
            country="Brasil",
            homicide_type="Homicídio simples",
            victim_count=3
        ),
        create_ranking_event(
            event_date=datetime(2026, 7, 16),
            state="RJ",
            country="Brasil",
            homicide_type="Feminicídio",
            victim_count=2
        ),
        create_ranking_event(
            event_date=datetime(2026, 7, 17),
            state="MG",
            country="Brasil",
            homicide_type="Latrocínio",
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
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # Types should have cells with victim counts
        assert "types" in data
        assert len(data["types"]) > 0
        
        # Sum victims across all types for July
        total_july_victims = 0
        for type_row in data["types"]:
            july_cell = next((c for c in type_row["cells"] if c["month"] == "2026-07"), None)
            if july_cell:
                total_july_victims += july_cell["victims"]
        
        # Should equal total victims from events
        assert total_july_victims == 6  # 3 + 2 + 1


@pytest.mark.asyncio
async def test_matrix_rankings_period_does_not_affect_matrix(app, async_session, population_fixture):
    """Test that rankings period query params do not change matrix months."""
    # Create events in July 2026
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",
            country="Brasil",
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
        # Matrix endpoint should ignore ranking-style period filters
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # Months should always start with "2026-07" regardless of any filters
        assert data["months"][0] == "2026-07"


@pytest.mark.asyncio
async def test_matrix_excludes_chile(app, async_session, population_fixture):
    """Test that matrix excludes Chilean events (BR only)."""
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",
            country="Brasil",
            victim_count=3
        ),
        create_ranking_event(
            event_date=datetime(2026, 7, 16),
            state="Metropolitana",  # Chilean region
            country="CL",  # Use ISO code as stored in database
            victim_count=5
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # UFs should only contain Brazilian states
        assert "ufs" in data
        for uf in data["ufs"]:
            # All UF abbrevs should be valid Brazilian states
            assert uf["abbrev"] in BRAZILIAN_STATES
        
        # Total victims in matrix should only be from Brasil
        total_victims = 0
        for uf in data["ufs"]:
            for cell in uf["cells"]:
                total_victims += cell["victims"]
        
        # Should only count the Brazilian event
        assert total_victims == 3


@pytest.mark.asyncio
async def test_matrix_all_27_ufs_present(app, async_session, population_fixture):
    """Test that all 27 Brazilian UFs are present even if they have no events."""
    # Create events only in SP
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",
            country="Brasil",
            victim_count=5
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # Should have exactly 27 UF rows
        assert len(data["ufs"]) == 27
        
        # All Brazilian states should be present
        uf_abbrevs = {uf["abbrev"] for uf in data["ufs"]}
        assert uf_abbrevs == set(BRAZILIAN_STATES)
        
        # SP should have victims
        sp_uf = next((uf for uf in data["ufs"] if uf["abbrev"] == "SP"), None)
        assert sp_uf is not None
        july_cell = next((c for c in sp_uf["cells"] if c["month"] == "2026-07"), None)
        assert july_cell["victims"] == 5
        
        # AC (first alphabetically) should have 0 victims
        ac_uf = next((uf for uf in data["ufs"] if uf["abbrev"] == "AC"), None)
        assert ac_uf is not None
        ac_july_cell = next((c for c in ac_uf["cells"] if c["month"] == "2026-07"), None)
        assert ac_july_cell["victims"] == 0


@pytest.mark.asyncio
async def test_matrix_leftover_types_in_outro(app, async_session, population_fixture):
    """Test that types not in canonical list go into Outro row."""
    events = [
        create_ranking_event(
            event_date=datetime(2026, 7, 15),
            state="SP",
            country="Brasil",
            homicide_type="Homicídio simples",
            victim_count=3
        ),
        create_ranking_event(
            event_date=datetime(2026, 7, 16),
            state="RJ",
            country="Brasil",
            homicide_type="Tipo não canônico A",  # Not in canonical list
            victim_count=2
        ),
        create_ranking_event(
            event_date=datetime(2026, 8, 1),
            state="MG",
            country="Brasil",
            homicide_type="Tipo não canônico B",  # Not in canonical list
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
        response = await client.get("/api/public/stats/matrix")
        assert response.status_code == 200
        data = response.json()
        
        # Should have canonical types plus Outro
        type_names = [t["type"] for t in data["types"]]
        assert "Homicídio simples" in type_names
        assert "Outro" in type_names
        
        # Outro should have the leftover victims
        outro = next((t for t in data["types"] if t["type"] == "Outro"), None)
        assert outro is not None
        
        july_cell = next((c for c in outro["cells"] if c["month"] == "2026-07"), None)
        assert july_cell["victims"] == 2  # From tipo não canônico A
        
        aug_cell = next((c for c in outro["cells"] if c["month"] == "2026-08"), None)
        assert aug_cell["victims"] == 1  # From tipo não canônico B


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


@pytest.mark.asyncio
async def test_city_size_floor_excludes_small_towns(app, async_session):
    """Test that small non-capital towns are excluded from rankings (issue #186).
    
    Size floor: capitals + population > 100k + has Arquivo cases.
    Example: Matos Costa SC (pop 2,761, 3 victims, not a capital) must NOT appear.
    """
    from app.models.ibge_population import IBGEPopulation
    
    now = datetime.utcnow()
    current_start = now - timedelta(days=365)
    
    # Create events for different city types
    events = [
        # Capital city (always included)
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            city="Florianópolis",
            state="SC",
            victim_count=2
        ),
        # Small town (pop 2,761, NOT a capital) - should be EXCLUDED
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            city="Matos Costa",
            state="SC",
            victim_count=3
        ),
        # Large city (pop > 100k, not a capital) - should be included
        create_ranking_event(
            event_date=current_start + timedelta(days=3),
            city="Joinville",
            state="SC",
            victim_count=1
        ),
    ]
    
    # Add population data
    # Real IBGE codes for these cities
    populations = [
        IBGEPopulation(code_muni=4205407, name_muni="Florianópolis", abbrev_state="SC", population=508826, year=2022),
        IBGEPopulation(code_muni=4210803, name_muni="Matos Costa", abbrev_state="SC", population=2761, year=2022),
        IBGEPopulation(code_muni=4209102, name_muni="Joinville", abbrev_state="SC", population=597658, year=2022),
    ]
    
    for event in events:
        async_session.add(event)
    for pop in populations:
        async_session.add(pop)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=365&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Extract city names from rankings
        city_names = [city["city"] for city in data["cities"]]
        
        # Florianópolis (capital) should be included
        assert "Florianópolis" in city_names, "Capital city should be included"
        
        # Joinville (pop > 100k) should be included
        assert "Joinville" in city_names, "Large city (pop > 100k) should be included"
        
        # Matos Costa (pop 2,761, not a capital) should be EXCLUDED
        assert "Matos Costa" not in city_names, "Small non-capital town (pop 2,761) must be excluded from rankings"


@pytest.mark.asyncio
async def test_states_filter_excludes_foreign_regions(app, async_session):
    """Test that only Brazilian states appear in states rankings (issue #186).
    
    Must exclude foreign regions like Síria, Flórida, OH, CA, Nova Jersey, etc.
    """
    now = datetime.utcnow()
    current_start = now - timedelta(days=365)
    
    # Create events in various locations
    events = [
        # Brazilian states (should be included)
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            country="BR",
            state="RJ",
            city="Rio de Janeiro",
            victim_count=2
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            country="BR",
            state="SP",
            city="São Paulo",
            victim_count=3
        ),
        # Foreign region (should be EXCLUDED)
        create_ranking_event(
            event_date=current_start + timedelta(days=3),
            country="BR",
            state="Síria",
            city="Damasco",
            victim_count=1,
            latitude=Decimal("33.5138"),
            longitude=Decimal("36.2765")
        ),
        # US states (should be EXCLUDED)
        create_ranking_event(
            event_date=current_start + timedelta(days=4),
            country="BR",
            state="Flórida",
            city="Miami",
            victim_count=1,
            latitude=Decimal("25.7617"),
            longitude=Decimal("-80.1918")
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=5),
            country="BR",
            state="OH",
            city="Cleveland",
            victim_count=1,
            latitude=Decimal("41.4993"),
            longitude=Decimal("-81.6944")
        ),
        # Mexican state (should be EXCLUDED)
        create_ranking_event(
            event_date=current_start + timedelta(days=6),
            country="BR",
            state="Jalisco",
            city="Guadalajara",
            victim_count=2,
            latitude=Decimal("20.6597"),
            longitude=Decimal("-103.3496")
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=365&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Extract state names from rankings
        state_names = [state["state"] for state in data["states"]]
        
        # Brazilian states should be included
        assert "RJ" in state_names, "Brazilian state RJ should be included"
        assert "SP" in state_names, "Brazilian state SP should be included"
        
        # Foreign regions should be EXCLUDED
        foreign_regions = ["Síria", "Flórida", "OH", "CA", "Nova Jersey", "Jalisco", "Guatemala", "Canindeyú"]
        for foreign in foreign_regions:
            assert foreign not in state_names, f"Foreign region '{foreign}' must be excluded from states rankings"


@pytest.mark.asyncio
async def test_rankings_default_sort_by_victims(app, async_session):
    """Test that rankings are sorted by victim count (not event count) by default (issue #186)."""
    now = datetime.utcnow()
    current_start = now - timedelta(days=365)
    
    # Create events with different victim/event ratios
    events = [
        # City A: 1 event, 5 victims (should be ranked #1)
        create_ranking_event(
            event_date=current_start + timedelta(days=1),
            city="São Paulo",
            state="SP",
            victim_count=5
        ),
        # City B: 3 events, 3 victims (should be ranked #2)
        create_ranking_event(
            event_date=current_start + timedelta(days=2),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=3),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=1
        ),
        create_ranking_event(
            event_date=current_start + timedelta(days=4),
            city="Rio de Janeiro",
            state="RJ",
            victim_count=1
        ),
        # City C: 1 event, 2 victims (should be ranked #3)
        create_ranking_event(
            event_date=current_start + timedelta(days=5),
            city="Belo Horizonte",
            state="MG",
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
        response = await client.get("/api/public/stats/rankings?days=365&country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Verify ranking order is by victim count
        assert len(data["cities"]) >= 3
        assert data["cities"][0]["city"] == "São Paulo", "São Paulo (5 victims) should be ranked #1"
        assert data["cities"][0]["victim_count"] == 5
        
        assert data["cities"][1]["city"] == "Rio de Janeiro", "Rio de Janeiro (3 victims) should be ranked #2"
        assert data["cities"][1]["victim_count"] == 3
        
        assert data["cities"][2]["city"] == "Belo Horizonte", "Belo Horizonte (2 victims) should be ranked #3"
        assert data["cities"][2]["victim_count"] == 2


