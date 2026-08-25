"""Tests for issue #179: Improved municipality code lookup with point-in-polygon and name folding."""

import pytest
from unittest.mock import AsyncMock, patch
from decimal import Decimal

from app.models.unique_event import UniqueEvent
from app.models.ibge_population import IBGEPopulation
from app.services.ibge_population import load_ibge_population_fixture, lookup_city_codes
from app.services.geocoding import geocode_unique_event
from app.services.municipality_codes import backfill_municipality_codes, set_test_mode


# Enable test fixture mode for all tests in this module
@pytest.fixture(autouse=True)
def use_test_fixture():
    """Ensure all tests use the small fixture, not production geobr polygons."""
    set_test_mode(True)
    yield
    set_test_mode(False)  # Reset after tests


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


# ========== Name-based lookup improvements (FALLBACK when no coordinates) ==========


@pytest.mark.asyncio
async def test_lookup_case_insensitive(async_session):
    """Test that lookup is case-insensitive: sao paulo / SAO PAULO → 3550308."""
    await load_ibge_population_fixture(async_session)
    
    # Test various case variations
    result = await lookup_city_codes(
        async_session,
        cities=["sao paulo", "SAO PAULO", "SaO pAuLo"],
        states=["SP", "SP", "SP"]
    )
    
    # All variations should resolve to São Paulo
    assert result.get(("sao paulo", "SP")) == 3550308
    assert result.get(("SAO PAULO", "SP")) == 3550308
    assert result.get(("SaO pAuLo", "SP")) == 3550308


@pytest.mark.asyncio
async def test_lookup_accent_insensitive(async_session):
    """Test that lookup is accent-insensitive: Sao Paulo → 3550308."""
    await load_ibge_population_fixture(async_session)
    
    result = await lookup_city_codes(
        async_session,
        cities=["Sao Paulo"],  # No tilde
        states=["SP"]
    )
    
    assert result.get(("Sao Paulo", "SP")) == 3550308


@pytest.mark.asyncio
async def test_lookup_accepts_full_state_name(async_session):
    """Test that lookup accepts full state name: Rio de Janeiro + Rio de Janeiro → 3304557."""
    await load_ibge_population_fixture(async_session)
    
    result = await lookup_city_codes(
        async_session,
        cities=["Rio de Janeiro"],
        states=["Rio de Janeiro"]  # Full state name, not "RJ"
    )
    
    assert result.get(("Rio de Janeiro", "Rio de Janeiro")) == 3304557


@pytest.mark.asyncio
async def test_lookup_unique_city_without_state(async_session):
    """Test that unique city without state gets code: Campinas (only in SP) → 3509502."""
    await load_ibge_population_fixture(async_session)
    
    # Test with city but no state - should return code if unique
    result = await lookup_city_codes(
        async_session,
        cities=["Campinas"],
        states=[None]  # No state provided
    )
    
    # Campinas appears only in SP in our fixture
    assert result.get(("Campinas", None)) == 3509502


@pytest.mark.asyncio
async def test_lookup_ambiguous_city_without_state_returns_empty(async_session):
    """Test that ambiguous city name without state returns empty (no guessing)."""
    # Add two cities with the same name in different states
    city_sp = IBGEPopulation(
        code_muni=3500001,
        code_state="35",
        name_muni="Teste",
        name_state="São Paulo",
        abbrev_state="SP",
        population=10000,
        year=2022,
        source="Test"
    )
    city_rj = IBGEPopulation(
        code_muni=3300001,
        code_state="33",
        name_muni="Teste",
        name_state="Rio de Janeiro",
        abbrev_state="RJ",
        population=15000,
        year=2022,
        source="Test"
    )
    async_session.add_all([city_sp, city_rj])
    await async_session.commit()
    
    result = await lookup_city_codes(
        async_session,
        cities=["Teste"],
        states=[None]  # No state - ambiguous!
    )
    
    # Should NOT return a code (ambiguous)
    assert ("Teste", None) not in result


@pytest.mark.asyncio
async def test_lookup_df_region_taguatinga_maps_to_brasilia(async_session):
    """Test that Taguatinga + DF → Brasília 5300108 (DF administrative region)."""
    # Add Brasília to the fixture
    brasilia = IBGEPopulation(
        code_muni=5300108,
        code_state="53",
        name_muni="Brasília",
        name_state="Distrito Federal",
        abbrev_state="DF",
        population=3094325,
        year=2022,
        source="IBGE Censo 2022 (fixture)"
    )
    async_session.add(brasilia)
    await async_session.commit()
    
    # Test DF administrative regions
    result = await lookup_city_codes(
        async_session,
        cities=["Taguatinga", "Ceilândia", "Samambaia"],
        states=["DF", "DF", "DF"]
    )
    
    # All DF regions should map to Brasília
    assert result.get(("Taguatinga", "DF")) == 5300108
    assert result.get(("Ceilândia", "DF")) == 5300108
    assert result.get(("Samambaia", "DF")) == 5300108


@pytest.mark.asyncio
async def test_lookup_no_city_returns_empty(async_session):
    """Test that events with no city get no code (do not invent)."""
    await load_ibge_population_fixture(async_session)
    
    result = await lookup_city_codes(
        async_session,
        cities=[None],
        states=["SP"]
    )
    
    assert (None, "SP") not in result


# ========== Point-in-polygon lookup (PRIMARY when coordinates exist) ==========


@pytest.mark.asyncio
async def test_geocode_with_coordinates_uses_polygon_lookup(async_session):
    """
    Test that when an event has lat/long, municipality code comes from point-in-polygon,
    NOT from the city name.
    
    Event with coordinates inside Rio polygon, city blank → 3304557
    """
    await load_ibge_population_fixture(async_session)
    
    # Create event with coordinates in Rio de Janeiro, but no city name
    event = UniqueEvent(
        city=None,  # Blank city!
        state="RJ",
        country="BR",
        event_family="homicidio",
        # Coordinates in Rio de Janeiro (Cristo Redentor area)
        latitude=Decimal("-22.9519"),
        longitude=Decimal("-43.2105")
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    
    # Run the municipality lookup (should use point-in-polygon)
    from app.services.municipality_codes import lookup_municipality_code_from_coordinates
    
    code = await lookup_municipality_code_from_coordinates(
        async_session,
        float(event.latitude),
        float(event.longitude)
    )
    
    assert code == 3304557, "Point in Rio polygon should return 3304557"


@pytest.mark.asyncio
async def test_geocode_taguatinga_coordinates_return_brasilia(async_session):
    """
    Test that coordinates in Taguatinga (DF administrative region) → Brasília 5300108.
    """
    # Add Brasília to fixture
    brasilia = IBGEPopulation(
        code_muni=5300108,
        code_state="53",
        name_muni="Brasília",
        name_state="Distrito Federal",
        abbrev_state="DF",
        population=3094325,
        year=2022,
        source="IBGE Censo 2022 (fixture)"
    )
    async_session.add(brasilia)
    await async_session.commit()
    
    # Coordinates in Taguatinga (DF)
    event = UniqueEvent(
        city="Taguatinga",
        state="DF",
        country="BR",
        event_family="homicidio",
        latitude=Decimal("-15.8267"),
        longitude=Decimal("-48.0444")
    )
    async_session.add(event)
    await async_session.commit()
    await async_session.refresh(event)
    
    from app.services.municipality_codes import lookup_municipality_code_from_coordinates
    
    code = await lookup_municipality_code_from_coordinates(
        async_session,
        float(event.latitude),
        float(event.longitude)
    )
    
    assert code == 5300108, "Point in Taguatinga (DF) should return Brasília 5300108"


@pytest.mark.asyncio
async def test_coordinates_trump_name_matching(async_session):
    """
    TEST SPEC RULE: When coordinates exist, code MUST come from polygon, NEVER from name.
    
    Event with city=São Paulo, state=SP, but coordinates inside Rio polygon.
    Must return Rio code 3304557, NOT São Paulo code 3550308.
    
    This proves that point-in-polygon takes absolute priority over name matching.
    """
    await load_ibge_population_fixture(async_session)
    
    # Event with São Paulo name but Rio coordinates
    event = UniqueEvent(
        city="São Paulo",  # Name says São Paulo
        state="SP",
        country="BR",
        event_family="homicidio",
        # Coordinates inside Rio de Janeiro polygon (Cristo Redentor)
        latitude=Decimal("-22.9519"),
        longitude=Decimal("-43.2105"),
        municipality_code=None
    )
    async_session.add(event)
    await async_session.commit()
    
    # Run backfill
    result = await backfill_municipality_codes(async_session)
    
    await async_session.refresh(event)
    
    # MUST be Rio (3304557), NOT São Paulo (3550308)
    assert event.municipality_code == 3304557, \
        "Coordinates inside Rio polygon must return Rio code, ignoring São Paulo name"
    assert result["updated"] == 1


@pytest.mark.asyncio
async def test_coordinates_outside_all_polygons_no_name_fallback(async_session):
    """
    TEST SPEC RULE: If coordinates exist but point is not inside ANY polygon,
    leave municipality_code empty. Do NOT fall back to name matching.
    
    Event has city+state that would normally resolve via name matching,
    but coordinates are outside all known polygons → must stay empty.
    """
    await load_ibge_population_fixture(async_session)
    
    # Event with valid city+state but coordinates in the ocean (far from any land)
    event = UniqueEvent(
        city="Rio de Janeiro",
        state="RJ",
        country="BR",
        event_family="homicidio",
        # Coordinates in the Atlantic Ocean (no municipality)
        latitude=Decimal("-25.0"),
        longitude=Decimal("-40.0"),
        municipality_code=None
    )
    async_session.add(event)
    await async_session.commit()
    
    # Run backfill
    result = await backfill_municipality_codes(async_session)
    
    await async_session.refresh(event)
    
    # MUST stay empty - do NOT fall back to name matching when coords exist
    assert event.municipality_code is None, \
        "Coordinates outside all polygons must leave code empty, no name fallback"
    assert result["updated"] == 0


@pytest.mark.asyncio
async def test_backfill_prefers_coordinates_over_name(async_session):
    """
    Test that backfill uses point-in-polygon when coordinates exist,
    and falls back to name matching when coordinates are missing.
    """
    await load_ibge_population_fixture(async_session)
    
    # Add Brasília
    brasilia = IBGEPopulation(
        code_muni=5300108,
        code_state="53",
        name_muni="Brasília",
        name_state="Distrito Federal",
        abbrev_state="DF",
        population=3094325,
        year=2022,
        source="IBGE Censo 2022 (fixture)"
    )
    async_session.add(brasilia)
    await async_session.commit()
    
    # Event 1: Has coordinates in Rio, no city name → should use polygon
    event1 = UniqueEvent(
        city=None,
        state=None,
        country="BR",
        event_family="homicidio",
        latitude=Decimal("-22.9519"),
        longitude=Decimal("-43.2105"),
        municipality_code=None
    )
    
    # Event 2: No coordinates, has city+state → should use name matching
    event2 = UniqueEvent(
        city="São Paulo",
        state="SP",
        country="BR",
        event_family="homicidio",
        latitude=None,
        longitude=None,
        municipality_code=None
    )
    
    # Event 3: No coordinates, no city → should stay empty
    event3 = UniqueEvent(
        city=None,
        state="RJ",
        country="BR",
        event_family="homicidio",
        latitude=None,
        longitude=None,
        municipality_code=None
    )
    
    async_session.add_all([event1, event2, event3])
    await async_session.commit()
    
    # Run backfill
    result = await backfill_municipality_codes(async_session)
    
    await async_session.refresh(event1)
    await async_session.refresh(event2)
    await async_session.refresh(event3)
    
    # Event 1 should get Rio code from polygon (even though city is blank)
    assert event1.municipality_code == 3304557
    
    # Event 2 should get São Paulo code from name matching
    assert event2.municipality_code == 3550308
    
    # Event 3 should stay empty (no coordinates, no city)
    assert event3.municipality_code is None
    
    assert result["updated"] == 2


@pytest.mark.asyncio
async def test_existing_174_tests_stay_green(async_session):
    """
    Ensure that existing #174 tests still pass:
    - Rio de Janeiro + RJ → 3304557 via name matching
    - Chile/Colombia not coded
    - Ambiguous city+missing state when the name is not unique → empty
    """
    await load_ibge_population_fixture(async_session)
    
    # Test 1: Rio de Janeiro + RJ → 3304557
    result = await lookup_city_codes(
        async_session,
        cities=["Rio de Janeiro"],
        states=["RJ"]
    )
    assert result.get(("Rio de Janeiro", "RJ")) == 3304557
    
    # Test 2: Ambiguous city without state
    city_sp = IBGEPopulation(
        code_muni=3500001,
        code_state="35",
        name_muni="Ambíguo",
        name_state="São Paulo",
        abbrev_state="SP",
        population=10000,
        year=2022,
        source="Test"
    )
    city_rj = IBGEPopulation(
        code_muni=3300001,
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
    
    result_ambiguous = await lookup_city_codes(
        async_session,
        cities=["Ambíguo"],
        states=[None]
    )
    assert ("Ambíguo", None) not in result_ambiguous
    
    # Test 3: Chile not coded
    event_chile = UniqueEvent(
        city="Santiago",
        state="Metropolitana",
        country="CL",
        event_family="homicidio",
        municipality_code=None
    )
    async_session.add(event_chile)
    await async_session.commit()
    
    result_backfill = await backfill_municipality_codes(async_session)
    await async_session.refresh(event_chile)
    
    assert event_chile.municipality_code is None
