"""Tests for IBGE municipality code lookup and backfill (issue #174)."""

import pytest
from unittest.mock import AsyncMock, patch
from sqlmodel import select
from sqlalchemy import text

from app.models.unique_event import UniqueEvent
from app.models.ibge_population import IBGEPopulation
from app.services.ibge_population import load_ibge_population_fixture, lookup_city_codes
from app.services.geocoding import geocode_unique_event


class _TestSessionMaker:
    """Test session maker wrapper for patching async_session_maker."""
    
    def __init__(self, session):
        self._session = session
    
    def __call__(self):
        return self
    
    async def __aenter__(self):
        return self._session
    
    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_lookup_city_codes_returns_official_code(async_session):
    """
    Test that lookup_city_codes returns the correct 7-digit IBGE code for a
    unique city+state pair.
    
    Fixture includes Rio de Janeiro, RJ → 3304557.
    """
    # Load fixture data (includes Rio de Janeiro = 3304557)
    await load_ibge_population_fixture(async_session)
    
    # Lookup Rio de Janeiro
    result = await lookup_city_codes(
        async_session,
        cities=["Rio de Janeiro"],
        states=["RJ"]
    )
    
    assert ("Rio de Janeiro", "RJ") in result
    assert result[("Rio de Janeiro", "RJ")] == 3304557


@pytest.mark.asyncio
async def test_lookup_city_codes_handles_ambiguous_cities(async_session):
    """
    Test that cities with the same name in different states are detected.
    
    We add two cities named "Teste" in different states (SP and RJ).
    The lookup should only return a code when the city+state pair is unique.
    """
    # Add two cities with the same name in different states
    city_sp = IBGEPopulation(
        code_muni=3500001,
        code_state="35",
        name_muni="Teste",
        name_state="São Paulo",
        abbrev_state="SP",
        population=10000,
        year=2022,
        source="Test fixture"
    )
    city_rj = IBGEPopulation(
        code_muni=3300001,
        code_state="33",
        name_muni="Teste",
        name_state="Rio de Janeiro",
        abbrev_state="RJ",
        population=15000,
        year=2022,
        source="Test fixture"
    )
    async_session.add(city_sp)
    async_session.add(city_rj)
    await async_session.commit()
    
    # Lookup Teste, SP - should return SP code
    result_sp = await lookup_city_codes(
        async_session,
        cities=["Teste"],
        states=["SP"]
    )
    assert ("Teste", "SP") in result_sp
    assert result_sp[("Teste", "SP")] == 3500001
    
    # Lookup Teste, RJ - should return RJ code
    result_rj = await lookup_city_codes(
        async_session,
        cities=["Teste"],
        states=["RJ"]
    )
    assert ("Teste", "RJ") in result_rj
    assert result_rj[("Teste", "RJ")] == 3300001
    
    # Both lookups should succeed because city+state pairs are unique


@pytest.mark.asyncio
async def test_geocode_stores_municipality_code_for_brazilian_city(async_session):
    """
    Test that when a UniqueEvent is geocoded for a Brazilian municipality,
    the municipality_code field is populated with the 7-digit IBGE code.
    
    Uses Rio de Janeiro as the test case (code 3304557).
    """
    # Load IBGE fixture (includes Rio de Janeiro = 3304557)
    await load_ibge_population_fixture(async_session)
    
    # Create a UniqueEvent with Rio de Janeiro location
    event = UniqueEvent(
        city="Rio de Janeiro",
        state="RJ",
        country="BR",
        event_family="homicidio"
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    
    # Mock Google Maps API response
    from unittest.mock import Mock
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={
        "status": "OK",
        "results": [{
            "formatted_address": "Rio de Janeiro, RJ, Brasil",
            "geometry": {
                "location": {"lat": -22.9068, "lng": -43.1729},
                "location_type": "APPROXIMATE",
            },
            "place_id": "ChIJW6AIkVXemwARTtIvZ2xC3FA",
            "types": ["locality", "political"],
        }],
    })
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    
    # Patch async_session_maker to use test session
    maker = _TestSessionMaker(async_session)
    
    # Geocode the event
    with (
        patch("app.services.geocoding.async_session_maker", maker),
        patch("app.services.geocoding.get_settings") as mock_settings,
    ):
        mock_settings.return_value.google_maps_api_key = "test-key"
        success = await geocode_unique_event(event.id, client=mock_client)
    
    assert success is True
    
    # Verify the municipality_code was set
    await async_session.refresh(event)
    assert event.municipality_code == 3304557, f"Expected 3304557, got {event.municipality_code}"
    assert event.city == "Rio de Janeiro"
    assert event.state == "RJ"
    assert event.latitude is not None


@pytest.mark.asyncio
async def test_geocode_no_code_for_chile_cities(async_session):
    """
    Test that Chilean cities do not get a municipality_code (Brazil only).
    """
    # Create a UniqueEvent with Chilean location
    event = UniqueEvent(
        city="Santiago",
        state="Metropolitana",
        country="CL",
        event_family="homicidio"
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    
    # Mock Google Maps API response for Santiago, Chile
    from unittest.mock import Mock
    mock_response = Mock()
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value={
        "status": "OK",
        "results": [{
            "formatted_address": "Santiago, Región Metropolitana, Chile",
            "geometry": {
                "location": {"lat": -33.4489, "lng": -70.6693},
                "location_type": "APPROXIMATE",
            },
            "place_id": "ChIJL68lS64hYpYRhB07b0sMDUw",
            "types": ["locality", "political"],
        }],
    })
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    
    # Patch async_session_maker to use test session
    maker = _TestSessionMaker(async_session)
    
    # Geocode the event
    with (
        patch("app.services.geocoding.async_session_maker", maker),
        patch("app.services.geocoding.get_settings") as mock_settings,
    ):
        mock_settings.return_value.google_maps_api_key = "test-key"
        success = await geocode_unique_event(event.id, client=mock_client)
    
    assert success is True
    
    # Verify NO municipality_code was set (Chile, not Brazil)
    await async_session.refresh(event)
    assert event.municipality_code is None
    assert event.country == "CL"
    assert event.latitude is not None


@pytest.mark.asyncio
async def test_backfill_municipality_codes_for_existing_events(async_session):
    """
    Test that existing UniqueEvents without municipality_code get codes
    backfilled when city+state uniquely resolve to an IBGE code.
    
    Tests the backfill path separate from the geocode path.
    """
    # Load IBGE fixture
    await load_ibge_population_fixture(async_session)
    
    # Create existing events without municipality_code but with city+state
    event1 = UniqueEvent(
        city="Rio de Janeiro",
        state="RJ",
        country="BR",
        event_family="homicidio",
        municipality_code=None  # Missing code
    )
    event2 = UniqueEvent(
        city="São Paulo",
        state="SP",
        country="BR",
        event_family="homicidio",
        municipality_code=None  # Missing code
    )
    # Event with no city - should not get a code
    event3 = UniqueEvent(
        city=None,
        state="RJ",
        country="BR",
        event_family="homicidio",
        municipality_code=None
    )
    # Chilean event - should not get a code
    event4 = UniqueEvent(
        city="Santiago",
        state="Metropolitana",
        country="CL",
        event_family="homicidio",
        municipality_code=None
    )
    
    async_session.add_all([event1, event2, event3, event4])
    await async_session.commit()
    
    # Import the backfill function (will be implemented)
    from app.services.municipality_codes import backfill_municipality_codes
    
    # Run backfill
    result = await backfill_municipality_codes(async_session)
    
    # Verify the results
    await async_session.refresh(event1)
    await async_session.refresh(event2)
    await async_session.refresh(event3)
    await async_session.refresh(event4)
    
    assert event1.municipality_code == 3304557, "Rio should get code 3304557"
    assert event2.municipality_code == 3550308, "São Paulo should get code 3550308"
    assert event3.municipality_code is None, "Event with no city should not get code"
    assert event4.municipality_code is None, "Chilean event should not get code"
    
    assert result["updated"] == 2, "Should have updated 2 events"
    assert result["skipped_no_city"] >= 1
    assert result["skipped_non_brazil"] >= 1


@pytest.mark.asyncio
async def test_backfill_does_not_update_non_brazil_events(async_session):
    """
    Test that backfill does NOT update events from other countries (CL, CO, etc).
    
    Regression test for SQL operator precedence bug where OR/AND without
    parentheses could pick up non-Brazil rows.
    """
    # Load IBGE fixture (Brazil codes only)
    await load_ibge_population_fixture(async_session)
    
    # Create a Chilean event with city+state
    event_cl = UniqueEvent(
        city="Santiago",
        state="Metropolitana",
        country="CL",
        event_family="homicidio",
        municipality_code=None
    )
    
    # Create a Colombian event with city+state
    event_co = UniqueEvent(
        city="Bogotá",
        state="Cundinamarca",
        country="CO",
        event_family="homicidio",
        municipality_code=None
    )
    
    # Create a Brazilian event with city+state (should get code)
    event_br = UniqueEvent(
        city="Rio de Janeiro",
        state="RJ",
        country="BR",
        event_family="homicidio",
        municipality_code=None
    )
    
    async_session.add_all([event_cl, event_co, event_br])
    await async_session.commit()
    
    from app.services.municipality_codes import backfill_municipality_codes
    
    # Run backfill
    result = await backfill_municipality_codes(async_session)
    
    # Refresh events
    await async_session.refresh(event_cl)
    await async_session.refresh(event_co)
    await async_session.refresh(event_br)
    
    # Non-Brazil events should NOT get codes
    assert event_cl.municipality_code is None, "Chilean event should not get IBGE code"
    assert event_co.municipality_code is None, "Colombian event should not get IBGE code"
    
    # Brazilian event SHOULD get the official code
    assert event_br.municipality_code == 3304557, "Rio de Janeiro should get code 3304557"
    
    # Verify counts
    assert result["updated"] == 1, "Only the Brazilian event should be updated"
    assert result["skipped_non_brazil"] >= 2, "Should skip at least CL and CO events"


@pytest.mark.asyncio
async def test_backfill_handles_ambiguous_city_names(async_session):
    """
    Test that backfill does NOT invent codes for ambiguous city names.
    
    If a city name appears in multiple states, we cannot guess which one
    the event refers to (unless we have the state).
    """
    # Add an ambiguous city name in two states
    city_sp = IBGEPopulation(
        code_muni=3500002,
        code_state="35",
        name_muni="Ambíguo",
        name_state="São Paulo",
        abbrev_state="SP",
        population=10000,
        year=2022,
        source="Test"
    )
    city_rj = IBGEPopulation(
        code_muni=3300002,
        code_state="33",
        name_muni="Ambíguo",
        name_state="Rio de Janeiro",
        abbrev_state="RJ",
        population=15000,
        year=2022,
        source="Test"
    )
    async_session.add_all([city_sp, city_rj])
    await async_session.commit()
    
    # Create an event with city but NO state - ambiguous
    event_no_state = UniqueEvent(
        city="Ambíguo",
        state=None,  # Missing state!
        country="BR",
        event_family="homicidio",
        municipality_code=None
    )
    
    # Create an event with city AND state - unambiguous
    event_with_state = UniqueEvent(
        city="Ambíguo",
        state="SP",
        country="BR",
        event_family="homicidio",
        municipality_code=None
    )
    
    async_session.add_all([event_no_state, event_with_state])
    await async_session.commit()
    
    from app.services.municipality_codes import backfill_municipality_codes
    
    # Run backfill
    result = await backfill_municipality_codes(async_session)
    
    await async_session.refresh(event_no_state)
    await async_session.refresh(event_with_state)
    
    # Event without state should NOT get a code (ambiguous)
    assert event_no_state.municipality_code is None, "Ambiguous city without state should not get code"
    
    # Event with state should get the correct code
    assert event_with_state.municipality_code == 3500002, "Unambiguous city+state should get code"
    
    assert result["updated"] == 1, "Only the unambiguous event should be updated"
