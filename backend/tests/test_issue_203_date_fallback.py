"""
TDD RED test for issue #203: Date fallback when extraction leaves date NULL.

Production symptom: date_time.date = None, date_precision = "não informada"
But story text contains explicit calendar dates like "15 de agosto de 2026".

The heuristic should recover these explicit dates as a fallback.
"""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

from app.models.unique_event import UniqueEvent
from app.services.extraction import raw_event_fields_from_event
from app.services.extraction_heuristics import apply_extraction_heuristics
from app.services.extraction_schemas import (
    DateTime,
    DateVerification,
    HomicideDynamic,
    IdentifiableVictim,
    Location,
    Victims,
    ViolentDeathEvent,
)


def test_argentina_null_date_with_explicit_date_in_text():
    """
    GREEN: Argentina event where extraction left date NULL,
    but story contains explicit date "15 de agosto de 2026".
    
    Heuristic recovers the date from text.
    """
    # Story with explicit Spanish date
    content = """
    Un hombre de 35 años fue asesinado a tiros el viernes 15 de agosto de 2026
    en el barrio de San Telmo, Buenos Aires. La víctima recibió múltiples
    disparos cuando salía de su domicilio alrededor de las 22h.
    """
    
    metadata = {
        "headline": "Hombre asesinado a tiros en San Telmo",
        "publisher": "Clarín",
        "url": "https://clarin.com/policiales/hombre-asesinado.html",
        "published_at": "2026-08-17T10:00:00Z",
    }
    
    # Extraction failed to get date (production symptom)
    event = ViolentDeathEvent(
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        location_info=Location(
            city="Buenos Aires",
            state="Buenos Aires",
            neighborhood="San Telmo",
            country="AR",
        ),
        date_time=DateTime(
            date=None,  # NULL - extraction failed
            date_precision="não informada",  # Production value
            time_of_day="noite",
            date_verification=DateVerification(
                has_explicit_date=False,
                date_source="none",
                year_explicitly_mentioned=False,
                verification_reasoning="LLM did not extract date",
            ),
        ),
        victims=Victims(
            identifiable_victims=[IdentifiableVictim(name="Carlos Rodríguez")],
            number_of_identifiable_victims=1,
            number_of_victims=1,
        ),
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO - SAN TELMO",
            method="Arma de fogo",
            chronological_description="Vítima foi morta a tiros.",
        ),
    )
    
    # Apply heuristics - should recover date from text
    fixed_event = apply_extraction_heuristics(event, content, metadata)
    
    # GREEN: Heuristic recovers explicit date from text
    assert fixed_event.date_time.date is not None, \
        "Heuristic should recover explicit date '15 de agosto de 2026' from text"
    
    assert fixed_event.date_time.date == "2026-08-15", \
        f"Expected 2026-08-15, got {fixed_event.date_time.date}"
    
    # Persist should work
    raw_fields = raw_event_fields_from_event(fixed_event)
    assert raw_fields["event_date"] == datetime(2026, 8, 15), \
        "event_date should be 2026-08-15 after heuristic recovery"


def test_argentina_slash_format_date():
    """
    GREEN: Argentina event with numeric date format "15/08/2026".
    """
    content = """
    Un hombre fue asesinado a tiros el 15/08/2026 en Buenos Aires.
    La víctima recibió múltiples disparos en el barrio de Palermo.
    """
    
    metadata = {
        "published_at": "2026-08-17T10:00:00Z",
    }
    
    event = ViolentDeathEvent(
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        location_info=Location(
            city="Buenos Aires",
            state="Buenos Aires",
            country="AR",
        ),
        date_time=DateTime(
            date=None,  # NULL
            date_precision="não informada",
            date_verification=DateVerification(
                has_explicit_date=False,
                date_source="none",
                year_explicitly_mentioned=False,
                verification_reasoning="LLM did not extract",
            ),
        ),
        victims=Victims(
            identifiable_victims=[],
            number_of_identifiable_victims=0,
            number_of_victims=1,
        ),
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO - PALERMO",
            method="Arma de fogo",
            chronological_description="Vítima foi morta a tiros.",
        ),
    )
    
    fixed_event = apply_extraction_heuristics(event, content, metadata)
    
    # GREEN: Recovers numeric date
    assert fixed_event.date_time.date == "2026-08-15", \
        "Should recover date from '15/08/2026' format"


@pytest.mark.asyncio
async def test_recovered_date_appears_in_rankings(app, async_session):
    """
    GREEN: After heuristic recovers date, event should appear in rankings.
    """
    # Simulate: extraction left date NULL, heuristic recovered it
    now = datetime.utcnow()
    event_date = now - timedelta(days=30)
    
    ar_event = UniqueEvent(
        title="HOMICÍDIO - SAN TELMO - 15 AGOSTO",
        event_date=event_date,  # Recovered by heuristic
        country="AR",
        state="Buenos Aires",
        city="Buenos Aires",
        neighborhood="San Telmo",
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        homicide_type="Homicídio simples",
        method_of_death="Arma de fogo",
        victim_count=1,
        latitude=Decimal("-34.6037"),
        longitude=Decimal("-58.3816"),
        source_count=1,
    )
    
    async_session.add(ar_event)
    await async_session.commit()
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.get("/api/public/stats/rankings?days=365&country=AR")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_events"] >= 1, \
            "Argentina event with recovered date should appear in rankings"
        
        city_names = [city["city"] for city in data["cities"]]
        assert "Buenos Aires" in city_names


def test_chile_dated_event_unchanged_regression():
    """
    Regression: Chile events with dates should stay unchanged.
    """
    content = """
    Un hombre fue asesinado a tiros el 16 de agosto de 2026 en Santiago.
    """
    
    metadata = {
        "published_at": "2026-08-17T10:00:00Z",
    }
    
    # Chile event with date already present
    event = ViolentDeathEvent(
        event_family="homicidio",
        event_subtype="simples",
        content_class="incident",
        location_info=Location(
            city="Santiago",
            state="Metropolitana",
            country="CL",
        ),
        date_time=DateTime(
            date="2026-08-16",  # Already has date
            date_precision="exata",
            date_verification=DateVerification(
                has_explicit_date=True,
                date_source="explicit",
                year_explicitly_mentioned=True,
                verification_reasoning="Extracted correctly",
            ),
        ),
        victims=Victims(
            identifiable_victims=[IdentifiableVictim(name="Juan Contreras")],
            number_of_identifiable_victims=1,
            number_of_victims=1,
        ),
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO - SANTIAGO",
            method="Arma de fogo",
            chronological_description="Vítima foi morta a tiros.",
        ),
    )
    
    # Heuristics should not break existing correct date
    fixed_event = apply_extraction_heuristics(event, content, metadata)
    
    assert fixed_event.date_time.date == "2026-08-16", \
        "Chile date should remain unchanged (regression)"
    
    raw_fields = raw_event_fields_from_event(fixed_event)
    assert raw_fields["event_date"] == datetime(2026, 8, 16)
