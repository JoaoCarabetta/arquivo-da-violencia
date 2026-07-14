"""Tests for derive_public_fields and related extraction derivations."""

from app.services.extraction_derived import derive_public_fields
from app.services.extraction_schemas import (
    CriminalGroupContext,
    DateTime,
    DateVerification,
    HomicideDynamic,
    IdentifiableVictim,
    Location,
    PoliticalRole,
    PoliceOperationContext,
    Victims,
    ViolentDeathEvent,
)


def _date_time() -> DateTime:
    return DateTime(
        date_verification=DateVerification(
            has_explicit_date=False,
            date_source="none",
            year_explicitly_mentioned=False,
            verification_reasoning="No date",
        ),
        date=None,
    )


def _base_event(**dynamic_kwargs) -> ViolentDeathEvent:
    dynamic_defaults = {
        "title": "HOMICÍDIO - RIO - DATA NÃO INFORMADA",
        "chronological_description": "Vítima morta a tiros.",
    }
    dynamic_defaults.update(dynamic_kwargs)
    return ViolentDeathEvent(
        event_family="homicidio",
        event_subtype="simples",
        location_info=Location(city="Rio de Janeiro", state="RJ"),
        date_time=_date_time(),
        victims=Victims(
            identifiable_victims=[IdentifiableVictim(name="João")],
            number_of_identifiable_victims=1,
            number_of_victims=1,
        ),
        homicide_dynamic=HomicideDynamic(**dynamic_defaults),
    )


def test_derive_criminal_group_fields():
    event = _base_event(
        criminal_group_context=CriminalGroupContext(
            connected=True,
            groups=["Comando Vermelho", "milícia"],
            activity="territorial-dispute",
            group_attacked="milícia",
        ),
    )
    fields = derive_public_fields(event)
    assert fields["criminal_group_connected"] is True
    assert fields["criminal_group_activity"] == "territorial-dispute"
    assert fields["criminal_groups"] == "Comando Vermelho; milícia"
    assert fields["criminal_group_attacked"] == "milícia"


def test_derive_politician_victim_fields():
    event = _base_event()
    event.victims.identifiable_victims[0].political_role = PoliticalRole(
        is_politician_or_candidate=True,
        status="elected",
        office="vereador",
        party="PT",
    )
    fields = derive_public_fields(event)
    assert fields["politician_or_candidate_victim"] is True
    assert fields["victim_political_status"] == "elected"
    assert fields["victim_political_office"] == "vereador"
    assert fields["victim_political_party"] == "PT"


def test_derive_police_operation_and_off_duty():
    event = _base_event(
        police_operation_context=PoliceOperationContext(
            connected=True,
            responsible_force="PM",
            targeted_armed_groups=True,
            operation_name="Operação Verão",
        ),
        off_duty_police_perpetrator=False,
        off_duty_police_context=None,
    )
    fields = derive_public_fields(event)
    assert fields["police_operation_connected"] is True
    assert fields["police_operation_force"] == "PM"
    assert fields["police_operation_targeted_armed_groups"] is True
    assert fields["off_duty_police_perpetrator"] is False


def test_activity_implies_connected_when_null():
    event = _base_event(
        criminal_group_context=CriminalGroupContext(
            connected=None,
            activity="retaliatory",
            groups=["PCC"],
        ),
    )
    fields = derive_public_fields(event)
    assert fields["criminal_group_connected"] is True
    assert fields["criminal_group_activity"] == "retaliatory"


def test_derive_security_force_victim_public_field():
    event = _base_event()
    event.victims.identifiable_victims[0].is_security_force = True
    fields = derive_public_fields(event)
    assert fields["security_force_victim"] is True
    assert fields["security_force_involved"] is True
