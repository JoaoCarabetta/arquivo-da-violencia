"""Tests for public stats endpoint."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

from app.models.unique_event import UniqueEvent


def create_fake_event(
    title: str = None,
    event_date: datetime | None = None,
    state: str = "RJ",
    city: str = "Rio de Janeiro",
    homicide_type: str = "Homicídio",
    victim_count: int = 1,
    **kwargs
) -> UniqueEvent:
    """Helper function to create a fake event for testing."""
    if title is None:
        title = f"Event in {city}, {state}"
    
    return UniqueEvent(
        title=title,
        event_date=event_date,
        state=state,
        city=city,
        neighborhood=kwargs.get("neighborhood"),
        homicide_type=homicide_type,
        method_of_death=kwargs.get("method_of_death", "Tiro"),
        victim_count=victim_count,
        identified_victim_count=kwargs.get("identified_victim_count"),
        victims_summary=kwargs.get("victims_summary", f"Vítima em {city}"),
        perpetrator_count=kwargs.get("perpetrator_count"),
        security_force_involved=kwargs.get("security_force_involved", False),
        chronological_description=kwargs.get("chronological_description", f"Descrição do evento em {city}"),
        latitude=kwargs.get("latitude", Decimal("-22.9068")),
        longitude=kwargs.get("longitude", Decimal("-43.1729")),
        source_count=kwargs.get("source_count", 1),
        confirmed=kwargs.get("confirmed", False),
        needs_enrichment=kwargs.get("needs_enrichment", False),
    )


@pytest.mark.asyncio
async def test_stats_total_no_events(client: AsyncClient):
    """Test total statistic with no events."""
    response = await client.get("/api/public/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["last_24h"] == 0
    assert data["last_7_days"] == 0
    assert data["last_30_days"] == 0


@pytest.mark.asyncio
async def test_stats_total_multiple_events(app, async_session):
    """Test total statistic counts all events including those with null event_date."""
    from app.database import get_session
    
    # Create events with and without event_date
    event1 = UniqueEvent(
        title="Event 1",
        event_date=datetime(2024, 1, 15, 10, 0, 0),
        state="RJ",
        city="Rio de Janeiro"
    )
    event2 = UniqueEvent(
        title="Event 2",
        event_date=datetime(2024, 2, 20, 14, 0, 0),
        state="SP",
        city="São Paulo"
    )
    event3 = UniqueEvent(
        title="Event 3",
        event_date=None,  # Null event_date should still be counted in total
        state="MG",
        city="Belo Horizonte"
    )
    
    async_session.add(event1)
    async_session.add(event2)
    async_session.add(event3)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3


@pytest.mark.asyncio
async def test_stats_last_24h_no_events_last_24h(app, async_session):
    """Test last_24h statistic with no events in last 24 hours."""
    from app.database import get_session
    
    # Create event from 25 hours ago (outside 24h window)
    event_25h_ago = datetime.utcnow() - timedelta(hours=25)
    event = UniqueEvent(
        title="Event 25 Hours Ago",
        event_date=event_25h_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    
    async_session.add(event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_24h"] == 0


@pytest.mark.asyncio
async def test_stats_last_24h_with_events_last_24h(app, async_session):
    """Test last_24h statistic counts only events from last 24 hours."""
    from app.database import get_session
    
    # Create events for different time periods
    now = datetime.utcnow()
    event_12h_ago = now - timedelta(hours=12)
    event_6h_ago = now - timedelta(hours=6)
    event_25h_ago = now - timedelta(hours=25)  # Outside 24h window
    event_future = now + timedelta(hours=1)  # Future event
    
    event_12h = UniqueEvent(
        title="Event 12 Hours Ago",
        event_date=event_12h_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_6h = UniqueEvent(
        title="Event 6 Hours Ago",
        event_date=event_6h_ago,
        state="SP",
        city="São Paulo"
    )
    event_25h = UniqueEvent(
        title="Event 25 Hours Ago",
        event_date=event_25h_ago,
        state="MG",
        city="Belo Horizonte"
    )
    event_future_event = UniqueEvent(
        title="Event Future",
        event_date=event_future,
        state="RS",
        city="Porto Alegre"
    )
    
    async_session.add(event_12h)
    async_session.add(event_6h)
    async_session.add(event_25h)
    async_session.add(event_future_event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_24h"] == 2  # Only events from last 24 hours


@pytest.mark.asyncio
async def test_stats_last_24h_excludes_null_event_date(app, async_session):
    """Test last_24h statistic excludes events with null event_date."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_12h_ago = now - timedelta(hours=12)
    
    event_recent = UniqueEvent(
        title="Event 12 Hours Ago",
        event_date=event_12h_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_null = UniqueEvent(
        title="Event Null Date",
        event_date=None,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_recent)
    async_session.add(event_null)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_24h"] == 1  # Only the event with a date in last 24h


@pytest.mark.asyncio
async def test_stats_last_7_days_no_events_last_7_days(app, async_session):
    """Test last_7_days statistic with no events in last 7 days."""
    from app.database import get_session
    
    # Create event from 8 days ago (outside 7 day window)
    event_8_days_ago = datetime.utcnow() - timedelta(days=8)
    
    event = UniqueEvent(
        title="Event 8 Days Ago",
        event_date=event_8_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    
    async_session.add(event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_7_days"] == 0


@pytest.mark.asyncio
async def test_stats_last_7_days_includes_recent_events(app, async_session):
    """Test last_7_days statistic includes events from last 7 days."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_1_day_ago = now - timedelta(days=1)
    event_3_days_ago = now - timedelta(days=3)
    
    event_recent1 = UniqueEvent(
        title="Event 1 Day Ago",
        event_date=event_1_day_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_recent2 = UniqueEvent(
        title="Event 3 Days Ago",
        event_date=event_3_days_ago,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_recent1)
    async_session.add(event_recent2)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_7_days"] == 2  # Both events within last 7 days


@pytest.mark.asyncio
async def test_stats_last_7_days_excludes_future_events(app, async_session):
    """Test last_7_days statistic excludes future events."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_1_day_ago = now - timedelta(days=1)
    event_future = now + timedelta(days=1)
    
    event_recent = UniqueEvent(
        title="Event 1 Day Ago",
        event_date=event_1_day_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_future_event = UniqueEvent(
        title="Event Future",
        event_date=event_future,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_recent)
    async_session.add(event_future_event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_7_days"] == 1  # Only recent event, not future


@pytest.mark.asyncio
async def test_stats_last_7_days_excludes_null_event_date(app, async_session):
    """Test last_7_days statistic excludes events with null event_date."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_2_days_ago = now - timedelta(days=2)
    
    event_recent = UniqueEvent(
        title="Event 2 Days Ago",
        event_date=event_2_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_null = UniqueEvent(
        title="Event Null Date",
        event_date=None,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_recent)
    async_session.add(event_null)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_7_days"] == 1  # Only the event with a date in last 7 days


@pytest.mark.asyncio
async def test_stats_last_7_days_edge_case_boundary(app, async_session):
    """Test last_7_days statistic at the 7-day boundary."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_6_days_ago = now - timedelta(days=6, hours=23)  # Just within 7 days
    event_7_days_1h_ago = now - timedelta(days=7, hours=1)  # Just outside 7 days
    
    event_within = UniqueEvent(
        title="Event Within 7 Days",
        event_date=event_6_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_outside = UniqueEvent(
        title="Event Outside 7 Days",
        event_date=event_7_days_1h_ago,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_within)
    async_session.add(event_outside)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        # Should include only the event within 7 days
        assert data["last_7_days"] >= 1


@pytest.mark.asyncio
async def test_stats_last_7_days_multiple_events(app, async_session):
    """Test last_7_days statistic with multiple events across the 7-day window."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_1_day_ago = now - timedelta(days=1)
    event_3_days_ago = now - timedelta(days=3)
    event_6_days_ago = now - timedelta(days=6)
    
    event1 = UniqueEvent(
        title="Event 1 Day Ago",
        event_date=event_1_day_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event2 = UniqueEvent(
        title="Event 3 Days Ago",
        event_date=event_3_days_ago,
        state="SP",
        city="São Paulo"
    )
    event3 = UniqueEvent(
        title="Event 6 Days Ago",
        event_date=event_6_days_ago,
        state="MG",
        city="Belo Horizonte"
    )
    
    async_session.add(event1)
    async_session.add(event2)
    async_session.add(event3)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        # Should include all three events within 7 days
        assert data["last_7_days"] >= 3


@pytest.mark.asyncio
async def test_stats_last_30_days_no_events_last_30_days(app, async_session):
    """Test last_30_days statistic with no events in last 30 days."""
    from app.database import get_session
    
    # Create event from 31 days ago (outside 30 day window)
    event_31_days_ago = datetime.utcnow() - timedelta(days=31)
    
    event = UniqueEvent(
        title="Event 31 Days Ago",
        event_date=event_31_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    
    async_session.add(event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_30_days"] == 0


@pytest.mark.asyncio
async def test_stats_last_30_days_includes_recent_events(app, async_session):
    """Test last_30_days statistic includes events from last 30 days."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_5_days_ago = now - timedelta(days=5)
    event_15_days_ago = now - timedelta(days=15)
    event_25_days_ago = now - timedelta(days=25)
    
    event1 = UniqueEvent(
        title="Event 5 Days Ago",
        event_date=event_5_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event2 = UniqueEvent(
        title="Event 15 Days Ago",
        event_date=event_15_days_ago,
        state="SP",
        city="São Paulo"
    )
    event3 = UniqueEvent(
        title="Event 25 Days Ago",
        event_date=event_25_days_ago,
        state="MG",
        city="Belo Horizonte"
    )
    
    async_session.add(event1)
    async_session.add(event2)
    async_session.add(event3)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_30_days"] == 3  # All three events within last 30 days


@pytest.mark.asyncio
async def test_stats_last_30_days_excludes_future_events(app, async_session):
    """Test last_30_days statistic excludes future events."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_10_days_ago = now - timedelta(days=10)
    event_future = now + timedelta(days=5)
    
    event_recent = UniqueEvent(
        title="Event 10 Days Ago",
        event_date=event_10_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_future_event = UniqueEvent(
        title="Event Future",
        event_date=event_future,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_recent)
    async_session.add(event_future_event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_30_days"] == 1  # Only recent event, not future


@pytest.mark.asyncio
async def test_stats_last_30_days_excludes_null_event_date(app, async_session):
    """Test last_30_days statistic excludes events with null event_date."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_10_days_ago = now - timedelta(days=10)
    
    event_recent = UniqueEvent(
        title="Event 10 Days Ago",
        event_date=event_10_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_null = UniqueEvent(
        title="Event Null Date",
        event_date=None,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_recent)
    async_session.add(event_null)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["last_30_days"] == 1  # Only the event with a date in last 30 days


@pytest.mark.asyncio
async def test_stats_last_30_days_edge_case_boundary(app, async_session):
    """Test last_30_days statistic at the 30-day boundary."""
    from app.database import get_session
    
    now = datetime.utcnow()
    event_29_days_ago = now - timedelta(days=29, hours=23)  # Just within 30 days
    event_30_days_1h_ago = now - timedelta(days=30, hours=1)  # Just outside 30 days
    
    event_within = UniqueEvent(
        title="Event Within 30 Days",
        event_date=event_29_days_ago,
        state="RJ",
        city="Rio de Janeiro"
    )
    event_outside = UniqueEvent(
        title="Event Outside 30 Days",
        event_date=event_30_days_1h_ago,
        state="SP",
        city="São Paulo"
    )
    
    async_session.add(event_within)
    async_session.add(event_outside)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/public/stats")
        assert response.status_code == 200
        data = response.json()
        # Should include only the event within 30 days
        assert data["last_30_days"] >= 1


def create_fake_event(
    title: str = None,
    event_date: datetime | None = None,
    state: str = "RJ",
    city: str = "Rio de Janeiro",
    homicide_type: str = "Homicídio",
    victim_count: int = 1,
    **kwargs
) -> UniqueEvent:
    """Helper function to create a fake event for testing."""
    from decimal import Decimal
    
    if title is None:
        title = f"Event in {city}, {state}"
    
    return UniqueEvent(
        title=title,
        event_date=event_date,
        state=state,
        city=city,
        neighborhood=kwargs.get("neighborhood"),
        homicide_type=homicide_type,
        method_of_death=kwargs.get("method_of_death", "Tiro"),
        victim_count=victim_count,
        identified_victim_count=kwargs.get("identified_victim_count"),
        victims_summary=kwargs.get("victims_summary", f"Vítima em {city}"),
        perpetrator_count=kwargs.get("perpetrator_count"),
        security_force_involved=kwargs.get("security_force_involved", False),
        chronological_description=kwargs.get("chronological_description", f"Descrição do evento em {city}"),
        latitude=kwargs.get("latitude", Decimal("-22.9068")),
        longitude=kwargs.get("longitude", Decimal("-43.1729")),
        source_count=kwargs.get("source_count", 1),
        confirmed=kwargs.get("confirmed", False),
        needs_enrichment=kwargs.get("needs_enrichment", False),
    )


@pytest.mark.asyncio
async def test_stats_with_multiple_fake_events(app, async_session):
    """Test statistics with a comprehensive set of fake events across different time periods."""
    from app.database import get_session
    
    # Use midnight for today to match the endpoint's calculation
    now = datetime.utcnow()
    event_10_min_ago = now - timedelta(minutes=10)
    event_12h_ago = now - timedelta(hours=12)
    event_1_day_ago = now - timedelta(days=1)
    event_3_days_ago = now - timedelta(days=3)
    event_15_days_ago = now - timedelta(days=15)
    event_8_days_ago = now - timedelta(days=8)  # Outside 7 days but within 30
    event_31_days_ago = now - timedelta(days=31)  # Outside 30 days
    event_future_1 = now + timedelta(days=1)
    event_future_2 = now + timedelta(days=10)
    
    # Create fake events for different time periods
    events = [
        # Very recent event (last 24h)
        create_fake_event(
            title="Homicídio há 10 minutos",
            event_date=event_10_min_ago,
            city="Rio de Janeiro",
            state="RJ",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        # Last 24h events
        create_fake_event(
            title="Homicídio há 12 horas",
            event_date=event_12h_ago,
            city="Rio de Janeiro",
            state="RJ",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        create_fake_event(
            title="Tentativa de homicídio há 6 horas",
            event_date=now - timedelta(hours=6),
            city="São Paulo",
            state="SP",
            homicide_type="Tentativa de Homicídio",
            victim_count=1,
        ),
        # Last 7 days events (but outside 24h)
        create_fake_event(
            title="Homicídio há 1 dia",
            event_date=event_1_day_ago,
            city="Belo Horizonte",
            state="MG",
            homicide_type="Homicídio",
            victim_count=2,
        ),
        create_fake_event(
            title="Homicídio há 3 dias",
            event_date=event_3_days_ago,
            city="Salvador",
            state="BA",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        # Last 30 days events (but outside 7 days)
        create_fake_event(
            title="Homicídio há 8 dias",
            event_date=event_8_days_ago,
            city="Porto Alegre",
            state="RS",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        create_fake_event(
            title="Homicídio há 15 dias",
            event_date=event_15_days_ago,
            city="Curitiba",
            state="PR",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        # Outside 30 days (should be excluded from all time-based stats)
        create_fake_event(
            title="Homicídio há 31 dias",
            event_date=event_31_days_ago,
            city="Brasília",
            state="DF",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        # Future events (should be excluded from all time-based stats)
        create_fake_event(
            title="Homicídio futuro",
            event_date=event_future_1,
            city="Recife",
            state="PE",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        create_fake_event(
            title="Homicídio futuro 2",
            event_date=event_future_2,
            city="Fortaleza",
            state="CE",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        # Event with null date (should be in total but not in time-based stats)
        create_fake_event(
            title="Evento sem data",
            event_date=None,
            city="Manaus",
            state="AM",
            homicide_type="Homicídio",
            victim_count=1,
        ),
        # Event with security force involved (within 24h)
        create_fake_event(
            title="Homicídio com policial envolvido",
            event_date=now - timedelta(hours=2),
            city="Rio de Janeiro",
            state="RJ",
            homicide_type="Homicídio",
            victim_count=1,
            security_force_involved=True,
        ),
        # Event with multiple victims (within 24h)
        create_fake_event(
            title="Massacre recente",
            event_date=now - timedelta(hours=4),
            city="São Paulo",
            state="SP",
            homicide_type="Homicídio",
            victim_count=5,
            identified_victim_count=3,
            victims_summary="Múltiplas vítimas identificadas",
        ),
    ]
    
    # Add all events to session
    for event in events:
        async_session.add(event)
    await async_session.commit()
    
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/public/stats")
            assert response.status_code == 200
            data = response.json()
            
            # Verify basic statistics
            assert data["total"] == 13  # All 13 events should be counted (added 10 min ago event)
            
            # Last 24h should include events from last 24 hours
            # We have: 1 event (10 min ago) + 2 events (12h ago, 6h ago) + 1 security force (2h ago) + 1 massacre (4h ago) = 5
            assert data["last_24h"] >= 5
            assert data["last_24h"] <= 5  # Exactly 5 events in last 24h
            
            # Last 7 days should include events from last 7 days
            # We have: 5 from last 24h + 1 from 1 day ago + 1 from 3 days ago = 7
            assert data["last_7_days"] >= 7
            assert data["last_7_days"] <= 7  # Exactly 7 events in last 7 days
            
            # Last 30 days should include events from last 30 days
            # We have: 7 from last 7 days + 1 from 8 days ago + 1 from 15 days ago = 9
            assert data["last_30_days"] >= 9
            assert data["last_30_days"] <= 9  # Exactly 9 events in last 30 days
            
            # Verify future events are excluded from time-based stats
            assert data["last_24h"] < data["total"]  # Future events excluded
            assert data["last_7_days"] < data["total"]  # Future events excluded
            assert data["last_30_days"] < data["total"]  # Future events excluded
            
            # Verify null date event is excluded from time-based stats
            # (it's included in total but not in time-based stats)
            assert data["last_24h"] < data["total"]  # Null date event excluded
            assert data["last_7_days"] < data["total"]  # Null date event excluded
            assert data["last_30_days"] < data["total"]  # Null date event excluded
            
            # Verify events outside 30 days are excluded
            # Event from 31 days ago should not be in last_30_days
            assert data["last_30_days"] == 9  # Should not include the 31-day-old event

