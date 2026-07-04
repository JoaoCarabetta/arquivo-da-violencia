"""Tests for extraction content_class and taxonomy prompts (AQV-33)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.extraction import content_class_failure_reason, extract_source
from app.services.extraction_schemas import (
    DateTime,
    DateVerification,
    HomicideDynamic,
    IdentifiableVictim,
    Location,
    Victims,
    ViolentDeathEvent,
)
from app.services import diagnostics


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def extraction_db(async_session):
    maker = _TestSessionMaker(async_session)
    with patch("app.services.extraction.async_session_maker", maker):
        with patch("app.services.diagnostics.async_session_maker", maker):
            yield async_session


def _minimal_event(**kwargs) -> ViolentDeathEvent:
    defaults = {
        "content_class": "incident",
        "location_info": Location(city="Rio de Janeiro", state="RJ"),
        "date_time": DateTime(
            date_verification=DateVerification(
                has_explicit_date=False,
                date_source="none",
                year_explicitly_mentioned=False,
                verification_reasoning="No date in text",
            ),
            date=None,
        ),
        "victims": Victims(
            identifiable_victims=[IdentifiableVictim(name="João")],
            number_of_identifiable_victims=1,
            number_of_victims=1,
        ),
        "homicide_dynamic": HomicideDynamic(
            title="HOMICÍDIO - RIO DE JANEIRO - DATA NÃO INFORMADA",
            homicide_type="Homicídio",
            chronological_description="Vítima foi morta a tiros.",
        ),
    }
    defaults.update(kwargs)
    return ViolentDeathEvent(**defaults)


def _source(**kwargs):
    from app.models.source_google_news import SourceGoogleNews, SourceStatus

    defaults = {
        "google_news_id": "extract-test",
        "google_news_url": "https://news.example/article",
        "resolved_url": "https://news.example/article",
        "headline": "Homem é morto a tiros em operação policial",
        "content": "Um homem foi morto a tiros durante operação policial.",
        "status": SourceStatus.extracting,
    }
    defaults.update(kwargs)
    return SourceGoogleNews(**defaults)


@pytest.mark.parametrize(
    "homicide_type",
    ["Intervenção policial", "Morte no trânsito"],
)
def test_homicide_type_accepts_new_values(homicide_type):
    event = _minimal_event(
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO - RIO DE JANEIRO - DATA NÃO INFORMADA",
            homicide_type=homicide_type,
            chronological_description="Vítima foi morta.",
        )
    )
    assert event.homicide_dynamic.homicide_type == homicide_type


@pytest.mark.parametrize(
    ("content_class", "expected_reason"),
    [
        ("aggregate_statistics", diagnostics.AGGREGATE_CONTENT),
        ("foreign", diagnostics.FOREIGN_CONTENT),
        ("non_incident", diagnostics.NON_INCIDENT_CONTENT),
        ("accident_disaster", diagnostics.NON_INCIDENT_CONTENT),
    ],
)
def test_content_class_failure_reason_mapping(content_class, expected_reason):
    assert content_class_failure_reason(content_class) == expected_reason


@pytest.mark.asyncio
async def test_extract_source_discards_non_incident_content_class(extraction_db):
    from app.models.source_google_news import SourceStatus

    source = _source(google_news_id="discard-foreign")
    extraction_db.add(source)
    await extraction_db.commit()
    await extraction_db.refresh(source)

    foreign_event = _minimal_event(content_class="foreign")

    with patch(
        "app.services.extraction.extract_event_from_content",
        return_value=foreign_event,
    ), patch(
        "app.services.extraction.diagnostics.count_attempts",
        new=AsyncMock(return_value=0),
    ), patch(
        "app.services.extraction.diagnostics.record_attempt",
        new=AsyncMock(),
    ) as mock_record:
        result = await extract_source(source.id)

    assert result is None
    await extraction_db.refresh(source)
    assert source.status == SourceStatus.discarded
    assert "content_class=foreign" in source.classification_reasoning
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["failure_reason"] == diagnostics.FOREIGN_CONTENT


@pytest.mark.asyncio
async def test_extract_source_persists_incident_with_content_class(extraction_db):
    from app.models.raw_event import RawEvent
    from app.models.source_google_news import SourceStatus
    from sqlmodel import select

    source = _source(google_news_id="persist-incident")
    extraction_db.add(source)
    await extraction_db.commit()
    await extraction_db.refresh(source)

    incident_event = _minimal_event(
        homicide_dynamic=HomicideDynamic(
            title="INTERVENÇÃO POLICIAL - ZONA NORTE - DATA NÃO INFORMADA",
            homicide_type="Intervenção policial",
            chronological_description="Suspeito foi morto em confronto com a polícia.",
        )
    )

    with patch(
        "app.services.extraction.extract_event_from_content",
        return_value=incident_event,
    ), patch(
        "app.services.extraction.diagnostics.count_attempts",
        new=AsyncMock(return_value=0),
    ), patch(
        "app.services.extraction.diagnostics.record_attempt",
        new=AsyncMock(),
    ):
        raw_event = await extract_source(source.id)

    assert raw_event is not None
    assert raw_event.content_class == "incident"
    assert raw_event.homicide_type == "Intervenção policial"

    await extraction_db.refresh(source)
    assert source.status == SourceStatus.extracted

    stored = (
        await extraction_db.exec(select(RawEvent).where(RawEvent.id == raw_event.id))
    ).one()
    assert stored.content_class == "incident"
