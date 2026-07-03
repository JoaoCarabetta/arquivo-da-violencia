"""Tests for content_class schema on RawEvent and UniqueEvent (AQV-28)."""

from datetime import datetime

from app.models.raw_event import RawEvent
from app.models.unique_event import UniqueEvent
from app.services.extraction_schemas import (
    ContentClass,
    DateTime,
    DateVerification,
    HomicideDynamic,
    IdentifiableVictim,
    Location,
    Victims,
    ViolentDeathEvent,
)


def _minimal_event(content_class: ContentClass = "incident") -> ViolentDeathEvent:
    return ViolentDeathEvent(
        content_class=content_class,
        location_info=Location(city="Rio de Janeiro", state="RJ"),
        date_time=DateTime(
            date_verification=DateVerification(
                has_explicit_date=False,
                date_source="none",
                year_explicitly_mentioned=False,
                verification_reasoning="No date in text",
            ),
            date=None,
        ),
        victims=Victims(
            identifiable_victims=[IdentifiableVictim(name="João")],
            number_of_identifiable_victims=1,
            number_of_victims=1,
        ),
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO - RIO DE JANEIRO - DATA NÃO INFORMADA",
            homicide_type="Homicídio",
            chronological_description="Vítima foi morta a tiros.",
        ),
    )


def test_unique_event_defaults_content_class_to_incident():
    event = UniqueEvent(title="Test", event_date=datetime.utcnow())
    assert event.content_class == "incident"


def test_unique_event_accepts_content_class_values():
    event = UniqueEvent(
        title="Stats report",
        event_date=datetime.utcnow(),
        content_class="aggregate_statistics",
    )
    assert event.content_class == "aggregate_statistics"


def test_raw_event_defaults_content_class_to_incident():
    event = RawEvent(title="Test", source_google_news_id=1)
    assert event.content_class == "incident"


def test_violent_death_event_accepts_content_class():
    event = _minimal_event(content_class="foreign")
    assert event.content_class == "foreign"


def test_violent_death_event_defaults_content_class_to_incident():
    event = _minimal_event()
    assert event.content_class == "incident"


def test_raw_event_persists_content_class_from_extraction_model():
    event = _minimal_event(content_class="aggregate_statistics")
    raw = RawEvent(
        title=event.homicide_dynamic.title,
        source_google_news_id=1,
        content_class=str(event.content_class),
        extraction_data=event.model_dump(),
    )
    assert raw.content_class == "aggregate_statistics"


def test_content_class_from_raw_event_prefers_column():
    from app.services.enrichment import _content_class_from_raw_event

    raw = RawEvent(
        title="Test",
        source_google_news_id=1,
        content_class="foreign",
        extraction_data={"content_class": "incident"},
    )
    assert _content_class_from_raw_event(raw) == "foreign"


def test_content_class_from_raw_event_falls_back_to_extraction_json():
    from app.services.enrichment import _content_class_from_raw_event

    raw = RawEvent(
        title="Test",
        source_google_news_id=1,
        content_class="incident",
        extraction_data={"content_class": "aggregate_statistics"},
    )
    assert _content_class_from_raw_event(raw) == "aggregate_statistics"
