"""Tests for public incident filters (homicide archive)."""

from app.services.public_filters import public_incident_criteria
from app.taxonomy import is_public_incident


def test_is_public_incident_homicide_only():
    assert is_public_incident("homicidio", "simples", content_class="incident", victim_count=1)
    assert not is_public_incident("tentativa", "simples", content_class="incident", victim_count=1)
    assert not is_public_incident("homicidio", "simples", content_class="aggregate_statistics")


def test_public_incident_criteria_includes_family_and_content_class():
    criteria = public_incident_criteria()
    assert len(criteria) == 4
