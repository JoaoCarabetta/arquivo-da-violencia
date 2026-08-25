"""Tests for query builder with country-specific terms."""

import pytest
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion import get_queries_for_city
from app.models import CityStats


@pytest.mark.asyncio
class TestCountryQueryBuilder:
    """Test query building for different countries."""
    
    async def test_ar_city_has_homicide_term(self, async_session: AsyncSession):
        """Argentina city query includes Spanish homicide terms."""
        queries = await get_queries_for_city("Buenos Aires", async_session, when="1h", country="AR")
        
        # Should be one query in standard mode (not sharded)
        assert len(queries) == 1
        query = queries[0]
        
        # Query should have the city name and when filter
        assert "Buenos Aires" in query
        assert "when:1h" in query
        
        # Query should include Spanish terms OR'd together
        assert "(" in query and ")" in query  # Parentheses for OR grouping
        assert "homicidio" in query.lower() or "asesinato" in query.lower()
    
    async def test_br_query_unchanged(self, async_session: AsyncSession):
        """Brazilian city query has no explicit terms (implicit context)."""
        queries = await get_queries_for_city("Rio de Janeiro RJ", async_session, when="1h", country="BR")
        
        # Should be one query in standard mode
        assert len(queries) == 1
        query = queries[0]
        
        # Query should have the city and when, but NO term filter
        assert "Rio de Janeiro RJ" in query
        assert "when:1h" in query
        assert "(" not in query  # No parenthesized term list
    
    async def test_gy_has_english_term(self, async_session: AsyncSession):
        """Guyana city query includes English homicide terms."""
        queries = await get_queries_for_city("Georgetown", async_session, when="1h", country="GY")
        
        # Should be one query in standard mode
        assert len(queries) == 1
        query = queries[0]
        
        # Query should have the city name
        assert "Georgetown" in query
        
        # Query should include English terms
        assert "(" in query and ")" in query
        query_lower = query.lower()
        assert "murder" in query_lower or "homicide" in query_lower or "killing" in query_lower
    
    async def test_co_city_has_spanish_terms(self, async_session: AsyncSession):
        """Colombian city query includes Spanish homicide terms."""
        queries = await get_queries_for_city("Bogotá", async_session, when="1h", country="CO")
        
        assert len(queries) == 1
        query = queries[0]
        
        assert "Bogotá" in query
        assert "homicidio" in query.lower() or "asesinato" in query.lower()
    
    async def test_sr_has_dutch_terms(self, async_session: AsyncSession):
        """Suriname city query includes Dutch homicide terms."""
        queries = await get_queries_for_city("Paramaribo", async_session, when="1h", country="SR")
        
        assert len(queries) == 1
        query = queries[0]
        
        assert "Paramaribo" in query
        query_lower = query.lower()
        assert "moord" in query_lower or "doodslag" in query_lower
