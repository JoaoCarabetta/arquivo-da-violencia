"""Tests for prod backfill candidate selection."""

from app.services.backfill import (
    _matches_signal,
    _target_status,
)
from app.services.classification_heuristics import should_force_violent_death


def test_heuristic_true_matches_crivado_de_balas():
    row = {
        "headline": (
            "Reagiu ao assalto: universitário não entrega o celular e é crivado de balas."
        ),
        "status": "discarded",
        "is_violent_death": False,
    }
    assert should_force_violent_death(row["headline"])
    assert _matches_signal(row, "heuristic_true")
    assert _matches_signal(row, "all")


def test_survival_headline_not_heuristic_true():
    row = {
        "headline": (
            "Jovem baleado na cabeça durante assalto tem quadro estável no hospital."
        ),
        "status": "discarded",
        "is_violent_death": False,
    }
    assert not should_force_violent_death(row["headline"])
    assert not _matches_signal(row, "heuristic_true")


def test_target_status_with_content():
    assert _target_status({"has_content": True}) == "ready_for_extraction"


def test_target_status_stored_violent_no_content():
    assert (
        _target_status({"has_content": False, "is_violent_death": True})
        == "ready_for_download"
    )


def test_target_status_default_reclassify():
    assert (
        _target_status({"has_content": False, "is_violent_death": False})
        == "ready_for_classification"
    )


def test_false_negative_signal():
    row = {
        "headline": "Some headline",
        "status": "discarded",
        "is_violent_death": True,
    }
    assert _matches_signal(row, "false_negative")
