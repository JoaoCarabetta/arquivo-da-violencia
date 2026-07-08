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
