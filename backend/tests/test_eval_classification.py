"""Tests for classification eval harness (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.schemas import CaseResult, load_fixture
from eval.stages.classification.score import score_case_results
from eval.stages.classification.validate import validate_fixture

SEED_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "eval" / "classification_seed.json"
)
HARD_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "eval" / "classification_hard.json"
)


@pytest.fixture
def seed_fixture():
    return load_fixture(json.loads(SEED_FIXTURE.read_text()))


def test_validate_seed_fixture(seed_fixture):
    result = validate_fixture(seed_fixture)
    assert result.valid is True
    assert result.labeled_count == 30
    assert result.pending_count == 0
    assert result.issues == []


def test_validate_hard_fixture():
    fixture = load_fixture(json.loads(HARD_FIXTURE.read_text()))
    result = validate_fixture(fixture)
    assert result.valid is True
    assert result.labeled_count == 30
    assert result.pending_count == 0


def test_validate_fails_on_labeled_without_expected():
    data = json.loads(SEED_FIXTURE.read_text())
    data["cases"][0]["expected"] = None
    fixture = load_fixture(data)
    result = validate_fixture(fixture)
    assert any("missing expected" in issue.message for issue in result.issues)


def test_validate_flags_pending_with_expected():
    data = json.loads(SEED_FIXTURE.read_text())
    data["cases"].append(
        {
            "id": "cls-pending-bad",
            "tags": ["negative"],
            "label_status": "pending",
            "input": {"headline": "Test headline"},
            "expected": {"is_violent_death": False},
            "metadata": {"source_id": None, "notes": ""},
        }
    )
    fixture = load_fixture(data)
    result = validate_fixture(fixture)
    assert any("pending case should have expected=null" in i.message for i in result.issues)


def test_score_perfect_run():
    results = [
        CaseResult(id="a", passed=True, expected=True, actual=True, tags=["clear_true"]),
        CaseResult(id="b", passed=True, expected=False, actual=False, tags=["clear_false"]),
    ]
    summary = score_case_results(results)
    assert summary.total == 2
    assert summary.passed == 2
    assert summary.accuracy == 1.0
    assert summary.precision == 1.0
    assert summary.recall == 1.0
    assert summary.f1 == 1.0
    assert summary.by_tag["clear_true"]["accuracy"] == 1.0


def test_score_false_positive_and_negative():
    results = [
        CaseResult(id="tp", passed=True, expected=True, actual=True),
        CaseResult(id="fp", passed=False, expected=False, actual=True),
        CaseResult(id="fn", passed=False, expected=True, actual=False),
        CaseResult(id="tn", passed=True, expected=False, actual=False),
    ]
    summary = score_case_results(results)
    assert summary.passed == 2
    assert summary.accuracy == 0.5
    assert summary.precision == 0.5
    assert summary.recall == 0.5
    assert summary.f1 == 0.5
