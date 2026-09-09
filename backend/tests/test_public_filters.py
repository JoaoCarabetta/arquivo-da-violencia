"""Tests for public incident filters (homicide archive)."""

from app.services.public_filters import is_brazilian_uf, public_incident_criteria
from app.taxonomy import is_public_incident


def test_is_public_incident_homicide_only():
    assert is_public_incident("homicidio", "simples", content_class="incident", victim_count=1)
    assert not is_public_incident("tentativa", "simples", content_class="incident", victim_count=1)
    assert not is_public_incident("homicidio", "simples", content_class="aggregate_statistics")


def test_public_incident_criteria_includes_family_and_content_class():
    criteria = public_incident_criteria()
    assert len(criteria) == 4


def test_is_brazilian_uf_accepts_codes_rejects_foreign_and_empty():
    assert is_brazilian_uf("SP")
    assert is_brazilian_uf("rj")
    assert is_brazilian_uf("BA")
    assert not is_brazilian_uf(None)
    assert not is_brazilian_uf("")
    assert not is_brazilian_uf("  ")
    assert not is_brazilian_uf("Colúmbia Britânica")
    assert not is_brazilian_uf("BC")
    assert not is_brazilian_uf("Síria")
    assert not is_brazilian_uf("São Paulo")
