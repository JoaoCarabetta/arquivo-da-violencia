"""Tests for content_class schema on RawEvent and UniqueEvent (AQV-28)."""

from datetime import datetime

from app.models.raw_event import RawEvent
from app.models.unique_event import UniqueEvent
from app.services.extraction_schemas import ViolentDeathEvent


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
    event = ViolentDeathEvent.model_validate(
        {
            "content_class": "foreign",
            "location_info": {
                "city": "Caracas",
                "state": None,
                "country": "Venezuela",
            },
            "date_time": {
                "date": "2025-01-01",
                "date_precision": "exata",
                "date_source": "texto",
            },
            "victims": {"count": 1, "identified_count": 0, "list": []},
            "homicide_dynamic": {
                "title": "HOMICÍDIO - CARACAS - 01/01/2025",
                "homicide_type": "Homicídio",
            },
        }
    )
    assert event.content_class == "foreign"
