"""Tests for shared official typology map (issue #239)."""

import pytest

from app.services.official_typology import (
    INDICATOR_MAPPING,
    MVI_INDICATORS,
    formulario_1_indicators,
    map_natureza,
)

# Fixture naturezas covering bag, extra, and unmapped cases
BAG_NATUREZAS = [
    ("Homicídio doloso", "homicidio_doloso"),
    ("Feminicídio", "feminicidio"),
    ("Roubo seguido de morte (latrocínio)", "latrocinio"),
    ("Lesão corporal seguida de morte", "lesao_corporal_seguida_morte"),
]

EXTRA_NATUREZA = (
    "Morte por intervenção de Agente do Estado",
    "morte_intervencao_policial",
)

UNKNOWN_NATUREZA = "Suicídio"


@pytest.mark.parametrize("natureza,indicator", BAG_NATUREZAS)
def test_map_natureza_bag_types(natureza, indicator):
    result = map_natureza(natureza)
    assert result["kind"] == "bag"
    assert result["indicator"] == indicator
    assert result["label"] == natureza


def test_map_natureza_extra_intervention():
    natureza, indicator = EXTRA_NATUREZA
    result = map_natureza(natureza)
    assert result["kind"] == "extra"
    assert result["indicator"] == indicator
    assert result["label"] == natureza


def test_map_natureza_unknown_unmapped():
    result = map_natureza(UNKNOWN_NATUREZA)
    assert result["kind"] == "unmapped"
    assert result["indicator"] is None
    assert result["label"] == "não mapeado"


def test_formulario_1_indicators_returns_four_bag_slugs():
    indicators = formulario_1_indicators()
    assert indicators == [
        "homicidio_doloso",
        "feminicidio",
        "latrocinio",
        "lesao_corporal_seguida_morte",
    ]


def test_mvi_indicators_matches_formulario_1():
    assert MVI_INDICATORS == formulario_1_indicators()


def test_indicator_mapping_exports_all_known_naturezas():
    for natureza, indicator in BAG_NATUREZAS:
        assert INDICATOR_MAPPING[natureza] == indicator
    natureza, indicator = EXTRA_NATUREZA
    assert INDICATOR_MAPPING[natureza] == indicator
