"""Tests for extraction validators and security_force mapping (AQV-30)."""

import pytest
from pydantic import ValidationError

from app.services.extraction_derived import derive_security_force_involved
from app.services.extraction_schemas import (
    DateTime,
    DateVerification,
    HomicideDynamic,
    IdentifiablePerpetrator,
    IdentifiableVictim,
    Location,
    Perpetrators,
    UnidentifiedVictimGroup,
    Victims,
    ViolentDeathEvent,
)


def _date_time(**kwargs) -> DateTime:
    defaults = {
        "date_verification": DateVerification(
            has_explicit_date=False,
            date_source="none",
            year_explicitly_mentioned=False,
            verification_reasoning="No date in text",
        ),
        "date": None,
    }
    defaults.update(kwargs)
    return DateTime(**defaults)


def _minimal_event(**victim_kwargs) -> ViolentDeathEvent:
    victim_defaults = {
        "identifiable_victims": [IdentifiableVictim(name="João")],
        "number_of_identifiable_victims": 1,
        "number_of_victims": 1,
    }
    victim_defaults.update(victim_kwargs)
    victims = Victims(**victim_defaults)
    return ViolentDeathEvent(
        event_family="homicidio",
        event_subtype="simples",
        location_info=Location(city="Rio de Janeiro", state="RJ"),
        date_time=_date_time(),
        victims=victims,
        homicide_dynamic=HomicideDynamic(
            title="HOMICÍDIO - RIO DE JANEIRO - DATA NÃO INFORMADA",
            chronological_description="Vítima foi morta a tiros.",
        ),
    )


def test_victims_rejects_count_above_20():
    with pytest.raises(ValidationError):
        Victims(
            identifiable_victims=[],
            number_of_identifiable_victims=0,
            number_of_victims=21,
        )


def test_victims_rejects_mismatched_identifiable_count():
    with pytest.raises(ValidationError, match="identifiable_victims list length"):
        Victims(
            identifiable_victims=[IdentifiableVictim(name="A")],
            number_of_identifiable_victims=2,
            number_of_victims=2,
        )


def test_victims_rejects_inconsistent_total():
    with pytest.raises(ValidationError, match="number_of_victims"):
        Victims(
            identifiable_victims=[IdentifiableVictim(name="A")],
            number_of_identifiable_victims=1,
            unidentified_groups=[UnidentifiedVictimGroup(count=5, description="moradores")],
            number_of_unidentified_victims=5,
            number_of_victims=10,
        )


def test_victims_allows_tolerance_of_one():
    victims = Victims(
        identifiable_victims=[IdentifiableVictim(name="A"), IdentifiableVictim(name="B")],
        number_of_identifiable_victims=2,
        number_of_victims=3,
    )
    assert victims.number_of_victims == 3


def test_derive_security_force_from_identifiable_victim():
    event = _minimal_event()
    event.victims.identifiable_victims[0].is_security_force = True
    assert derive_security_force_involved(event) is True


def test_derive_security_force_from_unidentified_group():
    event = _minimal_event(
        identifiable_victims=[],
        number_of_identifiable_victims=0,
        unidentified_groups=[
            UnidentifiedVictimGroup(count=2, description="policiais", is_security_force=True)
        ],
        number_of_unidentified_victims=2,
        number_of_victims=2,
    )
    assert derive_security_force_involved(event) is True


def test_derive_security_force_from_perpetrator():
    event = _minimal_event()
    event.perpetrators = Perpetrators(
        identifiable_perpetrators=[
            IdentifiablePerpetrator(name="PM", is_security_force=True)
        ],
        number_of_identifiable_perpetrators=1,
        number_of_perpetrators=1,
    )
    assert derive_security_force_involved(event) is True


def test_derive_security_force_returns_none_when_unmentioned():
    event = _minimal_event()
    assert derive_security_force_involved(event) is None


def test_derive_security_force_returns_false_when_explicitly_civilian():
    event = _minimal_event()
    event.victims.identifiable_victims[0].is_security_force = False
    assert derive_security_force_involved(event) is False
