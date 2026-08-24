"""Tests for query building at the get_queries_for_city seam.

Tests that Chilean queries include homicide terms while Brazilian queries remain unchanged.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.services.ingestion import get_queries_for_city


@pytest.mark.asyncio
async def test_chile_city_queries_include_homicide_term(async_session: AsyncSession):
    """Chile city queries must include at least one homicide vocabulary term."""
    # Given a Chilean city
    city = "Santiago Metropolitana"
    
    # When getting queries for that city
    queries = await get_queries_for_city(city, async_session, when="1h", country="CL")
    
    # Then at least one query should contain a homicide term
    homicide_terms = [
        "homicidio",
        "asesinato", 
        "femicidio",
        "feminicidio",
        "balacera",
        "tiroteo",
        "robo con homicidio",
        "muerte violenta",
        "operativo policial",
        "carabineros disparo",
    ]
    
    assert len(queries) > 0, "Should generate at least one query"
    
    # Check that at least one query contains at least one homicide term
    has_homicide_term = False
    for query in queries:
        if any(term in query.lower() for term in homicide_terms):
            has_homicide_term = True
            break
    
    assert has_homicide_term, (
        f"At least one Chile query must include a homicide term. Got: {queries}"
    )


@pytest.mark.asyncio
async def test_brazil_city_queries_unchanged(async_session: AsyncSession):
    """Brazilian city queries should remain unchanged (city + when only, no homicide terms)."""
    # Given a Brazilian city
    city = "Rio de Janeiro RJ"
    
    # When getting queries for that city in standard (non-sharded) mode
    queries = await get_queries_for_city(city, async_session, when="1h", country="BR")
    
    # Then the query should be exactly city + when (no additional terms)
    assert queries == ["Rio de Janeiro RJ when:1h"], (
        f"Brazil standard query should be unchanged. Got: {queries}"
    )


@pytest.mark.asyncio
async def test_brazil_city_sharded_queries_unchanged(async_session: AsyncSession):
    """Brazilian city sharded queries should remain unchanged (city + when + site only)."""
    # Given a Brazilian city that needs sharding
    city = "São Paulo SP"
    
    # First, set up the city to need sharding
    from app.models import CityStats
    stats = CityStats(city_name=city, needs_sharding=True)
    async_session.add(stats)
    await async_session.commit()
    
    # When getting queries for that city
    queries = await get_queries_for_city(city, async_session, when="1h", country="BR")
    
    # Then queries should be city + when + site (no homicide terms)
    assert len(queries) > 1, "Sharded mode should generate multiple queries"
    
    # All queries should match the pattern: "{city} when:{when} site:{source}"
    for query in queries:
        assert city in query, f"Query should contain city name: {query}"
        assert "when:1h" in query, f"Query should contain time filter: {query}"
        assert "site:" in query, f"Sharded query should contain site: {query}"
        
        # No homicide terms should be present
        homicide_terms = ["homicídio", "assassinato", "tiroteio"]
        assert not any(term in query.lower() for term in homicide_terms), (
            f"Brazil sharded queries should not have homicide terms: {query}"
        )
