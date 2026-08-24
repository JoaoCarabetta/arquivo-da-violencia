"""Tests for UniqueEvent country default (issue #152)."""

from datetime import datetime
from decimal import Decimal

import pytest
from sqlmodel import select

from app.models.unique_event import UniqueEvent


@pytest.mark.asyncio
async def test_unique_event_omit_country_defaults_to_br(async_session):
    """When country is omitted on insert, UniqueEvent defaults to BR, not Brasil."""
    event = UniqueEvent(
        title="Test event without country",
        event_date=datetime(2026, 8, 20, 10, 0, 0),
        state="SP",
        city="São Paulo",
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        # country is omitted - should default to "BR"
    )
    
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    
    # The stored country should be "BR", not "Brasil"
    assert event.country == "BR"


@pytest.mark.asyncio
async def test_unique_event_explicit_chile_country(async_session):
    """When country is explicitly set to CL, it should be stored as CL."""
    event = UniqueEvent(
        title="Evento en Chile",
        event_date=datetime(2026, 8, 20, 10, 0, 0),
        state="RM",
        city="Santiago",
        country="CL",  # Explicitly set to Chile
        latitude=Decimal("-33.4489"),
        longitude=Decimal("-70.6693"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
    )
    
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    
    # Chilean events should still store as "CL"
    assert event.country == "CL"


@pytest.mark.asyncio
async def test_public_country_filter_matches_iso_code(async_session):
    """Public country filter should match exact ISO code."""
    # Create a BR event (using default)
    br_event = UniqueEvent(
        title="Evento no Brasil",
        event_date=datetime(2026, 8, 20, 10, 0, 0),
        state="SP",
        city="São Paulo",
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        # country omitted, should default to "BR"
    )
    
    # Create a CL event
    cl_event = UniqueEvent(
        title="Evento en Chile",
        event_date=datetime(2026, 8, 20, 11, 0, 0),
        state="RM",
        city="Santiago",
        country="CL",
        latitude=Decimal("-33.4489"),
        longitude=Decimal("-70.6693"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
    )
    
    async_session.add_all([br_event, cl_event])
    await async_session.commit()
    
    # Query for CL events only
    result = await async_session.exec(
        select(UniqueEvent).where(UniqueEvent.country == "CL")
    )
    cl_events = result.all()
    
    # Should find only the Chilean event
    assert len(cl_events) == 1
    assert cl_events[0].country == "CL"
    assert cl_events[0].city == "Santiago"
    
    # Query for BR events only
    result = await async_session.exec(
        select(UniqueEvent).where(UniqueEvent.country == "BR")
    )
    br_events = result.all()
    
    # Should find only the Brazilian event
    assert len(br_events) == 1
    assert br_events[0].country == "BR"
    assert br_events[0].city == "São Paulo"


@pytest.mark.asyncio
async def test_country_filter_treats_legacy_brasil_as_br(async_session):
    """Querying for BR should also match legacy 'Brasil' values for backward compatibility."""
    # Create a legacy event with "Brasil"
    legacy_event = UniqueEvent(
        title="Evento legado",
        event_date=datetime(2026, 1, 15, 10, 0, 0),
        state="RJ",
        city="Rio de Janeiro",
        country="Brasil",  # Legacy value
        latitude=Decimal("-22.9068"),
        longitude=Decimal("-43.1729"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
    )
    
    # Create a new event with "BR"
    new_event = UniqueEvent(
        title="Evento novo",
        event_date=datetime(2026, 8, 20, 10, 0, 0),
        state="SP",
        city="São Paulo",
        # country omitted, should default to "BR"
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
    )
    
    # Create a Chilean event
    cl_event = UniqueEvent(
        title="Evento en Chile",
        event_date=datetime(2026, 8, 20, 11, 0, 0),
        state="RM",
        city="Santiago",
        country="CL",
        latitude=Decimal("-33.4489"),
        longitude=Decimal("-70.6693"),
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
    )
    
    async_session.add_all([legacy_event, new_event, cl_event])
    await async_session.commit()
    
    # When filtering by "BR" OR "Brasil", should get both BR events
    # This simulates the public API filter behavior
    from sqlmodel import or_
    result = await async_session.exec(
        select(UniqueEvent).where(
            or_(UniqueEvent.country == "BR", UniqueEvent.country == "Brasil")
        )
    )
    br_events = result.all()
    
    # Should find both the legacy "Brasil" and new "BR" events
    assert len(br_events) == 2
    cities = {e.city for e in br_events}
    assert cities == {"Rio de Janeiro", "São Paulo"}
    
    # Query for CL should still only match CL
    result = await async_session.exec(
        select(UniqueEvent).where(UniqueEvent.country == "CL")
    )
    cl_events = result.all()
    
    assert len(cl_events) == 1
    assert cl_events[0].city == "Santiago"
