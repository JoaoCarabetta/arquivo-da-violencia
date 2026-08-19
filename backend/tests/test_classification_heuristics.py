"""Unit tests for classification post-LLM heuristics."""

from app.services.classification import ViolentDeathClassification
from app.services.classification_heuristics import (
    apply_classification_heuristics,
    should_force_non_violent_death,
    should_force_violent_death,
)


def _result(is_violent_death: bool) -> ViolentDeathClassification:
    return ViolentDeathClassification(
        is_violent_death=is_violent_death,
        is_single_incident=True,
        confidence="média",
        reasoning="LLM baseline",
    )


def test_crivado_de_balas_forces_true():
    headline = (
        "Reagiu ao assalto: universitário não entrega o celular e é crivado de balas."
    )
    assert should_force_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(False))
    assert result.is_violent_death is True


def test_surviving_victim_forces_false():
    headline = (
        "Jovem baleado na cabeça durante assalto a padaria tem quadro estável no hospital."
    )
    assert should_force_non_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(True))
    assert result.is_violent_death is False


def test_troca_tiros_without_death_forces_false():
    headline = "Bope troca tiros com traficantes no Jacarezinho; caveirão é acionado."
    assert should_force_non_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(True))
    assert result.is_violent_death is False


def test_neutralizado_forces_true():
    headline = (
        "Confronto em comunidade termina com um neutralizado e três fuzis apreendidos."
    )
    assert should_force_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(False))
    assert result.is_violent_death is True


def test_nao_deixa_sobreviventes_not_treated_as_survival():
    headline = (
        "Chacina na madrugada: bando encapuzado invade residência e não deixa sobreviventes."
    )
    assert not should_force_non_violent_death(headline)
    assert should_force_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(False))
    assert result.is_violent_death is True


def test_morre_no_hospital_is_violent_death_not_survival():
    headline = "Homem baleado em Santo André não resiste e morre no hospital"
    assert not should_force_non_violent_death(headline)
    assert should_force_violent_death(headline)


# Country-aware heuristic tests for issue #129
def test_spanish_asesinato_forces_violent_death():
    """ES homicide headline with 'asesinato' should be classified as violent death."""
    headline = "Hombre asesinado a balazos en operativo policial en Santiago"
    assert should_force_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(False))
    assert result.is_violent_death is True


def test_us_shooting_foreign_marker_forces_false():
    """US shooting should be rejected by foreign heuristic."""
    headline = "Mass shooting in Texas leaves 5 dead"
    assert should_force_non_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(True))
    assert result.is_violent_death is False


def test_portuguese_homicide_sao_paulo_passes():
    """PT homicide in São Paulo should be classified as violent death."""
    headline = "Homem é morto a tiros em operação policial em São Paulo"
    assert should_force_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(False))
    assert result.is_violent_death is True


def test_spanish_sobrevivio_survivor_forces_false():
    """ES headline with 'sobrevivió' (survivor) should be rejected."""
    headline = "Hombre sobrevivió tras ser baleado en asalto"
    assert should_force_non_violent_death(headline)
    result = apply_classification_heuristics(headline, _result(True))
    assert result.is_violent_death is False


def test_chilean_carabineros_not_treated_as_foreign():
    """Carabineros marker should prevent Chilean police ops from being rejected as foreign.
    
    This tests that the presence of 'Carabineros' doesn't trigger foreign rejection,
    allowing Chilean police operations to be properly classified.
    """
    headline = "Carabineros detiene a sospechoso tras tiroteo en Santiago"
    # Should not be forced as non-violent (not foreign)
    assert not should_force_non_violent_death(headline)


def test_chilean_pdi_not_treated_as_foreign():
    """PDI marker should prevent Chilean police ops from being rejected as foreign.
    
    This tests that the presence of 'PDI' doesn't trigger foreign rejection,
    allowing Chilean police operations to be properly classified.
    """
    headline = "PDI investiga caso de femicidio en Valparaíso"
    # Should not be forced as non-violent (not foreign)
    assert not should_force_non_violent_death(headline)
    # And femicidio should force violent death
    assert should_force_violent_death(headline)
