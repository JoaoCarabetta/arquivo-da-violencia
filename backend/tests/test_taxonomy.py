"""Tests for app.taxonomy — event_family + event_subtype hierarchy."""

import pytest

from app.taxonomy import (
    TaxonomyValidationError,
    format_event_label,
    format_legacy_homicide_type,
    is_public_incident,
    parse_legacy_homicide_type,
    validate_family_subtype,
)


@pytest.mark.parametrize(
    ("family", "subtype"),
    [
        ("homicidio", "simples"),
        ("homicidio", "feminicidio"),
        ("homicidio", "intervencao_policial"),
        ("tentativa", "simples"),
        ("acidente_fatal", "culposo"),
        ("nao_classificado", "outro"),
    ],
)
def test_validate_family_subtype_accepts_valid_pairs(family, subtype):
    validate_family_subtype(family, subtype)


def test_validate_family_subtype_rejects_invalid_pair():
    with pytest.raises(TaxonomyValidationError):
        validate_family_subtype("homicidio", "culposo")


@pytest.mark.parametrize(
    ("legacy", "family", "subtype"),
    [
        ("Homicídio", "homicidio", "simples"),
        ("Homicídio Qualificado", "homicidio", "qualificado"),
        ("Feminicídio", "homicidio", "feminicidio"),
        ("Latrocínio", "homicidio", "latrocinio"),
        ("Intervenção policial", "homicidio", "intervencao_policial"),
        ("Morte no trânsito", "homicidio", "morte_transito_doloso"),
        ("Tentativa de Homicídio", "tentativa", "simples"),
        ("Homicídio Culposo", "acidente_fatal", "culposo"),
        ("Outro", "nao_classificado", "outro"),
        (None, "nao_classificado", "outro"),
    ],
)
def test_parse_legacy_homicide_type(legacy, family, subtype):
    assert parse_legacy_homicide_type(legacy) == (family, subtype)


def test_format_legacy_homicide_type_roundtrip():
    for legacy in ("Homicídio", "Feminicídio", "Tentativa de Homicídio", "Outro"):
        family, subtype = parse_legacy_homicide_type(legacy)
        assert format_legacy_homicide_type(family, subtype) == legacy


def test_format_event_label():
    assert format_event_label("homicidio", "feminicidio") == "Feminicídio"


def test_is_public_incident_homicide_only():
    assert is_public_incident("homicidio", "simples", content_class="incident", victim_count=1)
    assert not is_public_incident("tentativa", "simples", content_class="incident", victim_count=1)
    assert not is_public_incident("homicidio", "simples", content_class="aggregate_statistics")
    assert not is_public_incident("homicidio", "simples", content_class="incident", victim_count=50)
