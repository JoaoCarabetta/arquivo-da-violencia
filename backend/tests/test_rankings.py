"""Tests for /api/public/stats/rankings endpoint."""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

from app.models.unique_event import UniqueEvent
from app.taxonomy import parse_legacy_homicide_type


def create_ranking_event(
    country: str = "BR",
    state: str = "RJ",
    city: str = "Rio de Janeiro",
    event_date: datetime | None = None,
    victim_count: int = 1,
    **kwargs
) -> UniqueEvent:
    """Helper to create events for rankings tests."""
    if event_date is None:
        event_date = datetime.utcnow() - timedelta(days=15)
    
    family, subtype = parse_legacy_homicide_type("Homicídio")
    
    return UniqueEvent(
        title=f"Event in {city}, {state}, {country}",
        event_date=event_date,
        country=country,
        state=state,
        city=city,
        event_family=family,
        event_subtype=subtype,
        homicide_type="Homicídio",
        content_class="incident",
        method_of_death="Tiro",
        victim_count=victim_count,
        victims_summary=f"Vítima em {city}",
        chronological_description=f"Descrição do evento em {city}",
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
        source_count=1,
        confirmed=False,
        needs_enrichment=False,
    )


@pytest.mark.asyncio
async def test_rankings_chile_includes_chilean_states(app, async_session):
    """Chilean events with Chilean state names should be included in country=CL rankings."""
    from app.database import get_session
    
    now = datetime.utcnow()
    
    # Create Chilean event with Chilean region name
    chile_event = create_ranking_event(
        country="CL",
        state="Metropolitana",
        city="Conchalí",
        event_date=now - timedelta(days=10),
        victim_count=1,
    )
    
    async_session.add(chile_event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats/rankings?country=CL")
        assert response.status_code == 200
        data = response.json()
        
        # Should include the Chilean event
        assert data["total_events"] == 1
        assert data["total_victims"] == 1


@pytest.mark.asyncio
async def test_rankings_brazil_requires_valid_uf(app, async_session):
    """Brazilian events must have valid UF codes to be included in country=BR rankings."""
    from app.database import get_session
    
    now = datetime.utcnow()
    
    # Create Brazilian event with valid UF
    br_valid = create_ranking_event(
        country="BR",
        state="SP",
        city="São Paulo",
        event_date=now - timedelta(days=10),
        victim_count=1,
    )
    
    # Create Brazilian event with invalid state (Chilean region name)
    br_invalid = create_ranking_event(
        country="BR",
        state="Metropolitana",  # Invalid for Brazil
        city="São Paulo",
        event_date=now - timedelta(days=10),
        victim_count=1,
    )
    
    async_session.add(br_valid)
    async_session.add(br_invalid)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats/rankings?country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Should include only the valid UF event, not the invalid one
        assert data["total_events"] == 1
        assert data["total_victims"] == 1


@pytest.mark.asyncio
async def test_rankings_brazil_allows_null_state(app, async_session):
    """Brazilian events with null state should be included in country=BR rankings."""
    from app.database import get_session
    
    now = datetime.utcnow()
    
    # Create Brazilian event with null state
    br_null = create_ranking_event(
        country="BR",
        state=None,
        city="Unknown City",
        event_date=now - timedelta(days=10),
        victim_count=1,
    )
    
    async_session.add(br_null)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats/rankings?country=BR")
        assert response.status_code == 200
        data = response.json()
        
        # Should include the null state event
        assert data["total_events"] == 1
        assert data["total_victims"] == 1


@pytest.mark.asyncio
async def test_rankings_chile_mixed_states(app, async_session):
    """Rankings for Chile should include multiple Chilean regions."""
    from app.database import get_session
    
    now = datetime.utcnow()
    
    # Create events in different Chilean regions
    events = [
        create_ranking_event(
            country="CL",
            state="Metropolitana",
            city="Santiago",
            event_date=now - timedelta(days=10),
            victim_count=2,
        ),
        create_ranking_event(
            country="CL",
            state="Coquimbo",
            city="La Serena",
            event_date=now - timedelta(days=5),
            victim_count=1,
        ),
        create_ranking_event(
            country="CL",
            state="Valparaíso",
            city="Valparaíso",
            event_date=now - timedelta(days=3),
            victim_count=3,
        ),
    ]
    
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats/rankings?country=CL")
        assert response.status_code == 200
        data = response.json()
        
        # Should include all Chilean events
        assert data["total_events"] == 3
        assert data["total_victims"] == 6


@pytest.mark.asyncio
async def test_rankings_legacy_brasil_uses_br_filter(app, async_session):
    """Legacy country='Brasil' should use BR UF filter."""
    from app.database import get_session
    
    now = datetime.utcnow()
    
    # Create event with legacy Brasil country value and valid UF
    legacy_br = create_ranking_event(
        country="Brasil",
        state="RJ",
        city="Rio de Janeiro",
        event_date=now - timedelta(days=10),
        victim_count=1,
    )
    
    async_session.add(legacy_br)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Query with country=Brasil (legacy value)
        response = await client.get("/api/public/stats/rankings?country=Brasil")
        assert response.status_code == 200
        data = response.json()
        
        # Should include the event
        assert data["total_events"] == 1
        assert data["total_victims"] == 1


@pytest.mark.asyncio
async def test_rankings_country_isolation(app, async_session):
    """Rankings for one country should not include events from another country."""
    from app.database import get_session
    
    now = datetime.utcnow()
    
    # Create events in different countries
    br_event = create_ranking_event(
        country="BR",
        state="SP",
        city="São Paulo",
        event_date=now - timedelta(days=10),
        victim_count=1,
    )
    
    cl_event = create_ranking_event(
        country="CL",
        state="Metropolitana",
        city="Santiago",
        event_date=now - timedelta(days=10),
        victim_count=2,
    )
    
    async_session.add(br_event)
    async_session.add(cl_event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Check BR rankings
        response = await client.get("/api/public/stats/rankings?country=BR")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 1
        assert data["total_victims"] == 1
        
        # Check CL rankings
        response = await client.get("/api/public/stats/rankings?country=CL")
        assert response.status_code == 200
        data = response.json()
        assert data["total_events"] == 1
        assert data["total_victims"] == 2
