"""Tests for rankings with country-specific filtering."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unique_event import UniqueEvent
from main import app


@pytest.mark.asyncio
class TestCountryRankings:
    """Test rankings endpoint with multi-country support."""
    
    async def test_rankings_ar_counts_argentine_event(self, async_session: AsyncSession):
        """Rankings?country=AR counts an event with non-BR state."""
        # Create an Argentine event with a non-BR state name
        event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="AR",
            state="Buenos Aires",  # Argentine province, not a BR UF
            city="Buenos Aires",
            victim_count=1,
            latitude=-34.6037,
            longitude=-58.3816,
        )
        async_session.add(event)
        await async_session.commit()
        
        # Query rankings for Argentina
        client = TestClient(app)
        response = client.get("/public/stats/rankings?country=AR&days=30")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have at least one event in the current period
        assert "current_period" in data
        assert "countries" in data["current_period"]
        
        # Argentina should appear in countries list
        countries = data["current_period"]["countries"]
        ar_entry = next((c for c in countries if c["name"] == "Argentina"), None)
        assert ar_entry is not None
        assert ar_entry["victim_count"] >= 1
    
    async def test_rankings_br_excludes_non_br_states(self, async_session: AsyncSession):
        """Rankings?country=BR excludes events with non-BR state names."""
        # Create a BR event with a valid BR state
        br_event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="BR",
            state="RJ",  # Valid BR UF
            city="Rio de Janeiro",
            victim_count=1,
            latitude=-22.9068,
            longitude=-43.1729,
        )
        async_session.add(br_event)
        
        # Create a rogue event with BR country but non-BR state (should be filtered)
        rogue_event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="BR",
            state="Buenos Aires",  # NOT a valid BR UF
            city="São Paulo",
            victim_count=1,
            latitude=-23.5505,
            longitude=-46.6333,
        )
        async_session.add(rogue_event)
        
        await async_session.commit()
        
        # Query rankings for Brazil only
        client = TestClient(app)
        response = client.get("/public/stats/rankings?country=BR&days=30")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have states in the response
        states = data["current_period"].get("states", [])
        
        # RJ should appear (valid BR UF)
        rj_entry = next((s for s in states if "RJ" in str(s.get("name", ""))), None)
        assert rj_entry is not None
        
        # Buenos Aires should NOT appear (not a BR UF)
        ba_entry = next((s for s in states if "Buenos Aires" in str(s.get("name", ""))), None)
        assert ba_entry is None
    
    async def test_rankings_cl_allows_chilean_regions(self, async_session: AsyncSession):
        """Rankings?country=CL allows Chilean region names."""
        # Create a Chilean event with a Chilean region
        event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="CL",
            state="Metropolitana",  # Chilean region
            city="Santiago",
            victim_count=1,
            latitude=-33.4489,
            longitude=-70.6693,
        )
        async_session.add(event)
        await async_session.commit()
        
        # Query rankings for Chile
        client = TestClient(app)
        response = client.get("/public/stats/rankings?country=CL&days=30")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have countries in the response
        countries = data["current_period"]["countries"]
        cl_entry = next((c for c in countries if c["name"] == "Chile"), None)
        assert cl_entry is not None
        assert cl_entry["victim_count"] >= 1
    
    async def test_rankings_no_country_filter_accepts_all_sa(self, async_session: AsyncSession):
        """Rankings without country filter accepts all SA countries, including non-BR/CL states."""
        # Create events from multiple SA countries with their own state names
        br_event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="BR",
            state="SP",  # Valid BR UF
            city="São Paulo",
            victim_count=1,
            latitude=-23.5505,
            longitude=-46.6333,
        )
        ar_event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="AR",
            state="Buenos Aires",  # Argentine province (NOT a BR UF or CL region)
            city="Buenos Aires",
            victim_count=1,
            latitude=-34.6037,
            longitude=-58.3816,
        )
        co_event = UniqueEvent(
            event_family="homicidio",
            content_class="incident",
            event_date=datetime.utcnow() - timedelta(days=10),
            country="CO",
            state="Cundinamarca",  # Colombian department (NOT a BR UF or CL region)
            city="Bogotá",
            victim_count=1,
            latitude=4.7110,
            longitude=-74.0721,
        )
        async_session.add(br_event)
        async_session.add(ar_event)
        async_session.add(co_event)
        await async_session.commit()
        
        # Query rankings without country filter (unfiltered SA view)
        client = TestClient(app)
        response = client.get("/public/stats/rankings?days=30")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should have all three countries in the countries list
        countries = data["current_period"]["countries"]
        country_names = [c["name"] for c in countries]
        
        assert "Brasil" in country_names
        assert "Argentina" in country_names
        assert "Colombia" in country_names
