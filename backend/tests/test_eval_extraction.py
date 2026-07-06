"""Tests for extraction eval harness (no LLM)."""

from __future__ import annotations

from eval.schemas_extraction import (
    CaseScoring,
    ExtractionCase,
    ExtractionFixture,
    ExtractionFixtureMeta,
    ExtractionInput,
    ExtractionMetadata,
    validate_extraction_fixture,
)
from eval.stages.extraction.score import score_case


def _sample_case(**overrides) -> ExtractionCase:
    base = ExtractionCase(
        id="ext-test-001",
        tags=["short"],
        label_status="labeled",
        input=ExtractionInput(
            content="Texto",
            metadata=ExtractionMetadata(headline="Manchete"),
        ),
        expected={
            "date_time": {"date": "2025-03-14", "date_verification": {"has_explicit_date": True}},
            "location_info": {"city": "Rio de Janeiro", "state": "RJ"},
            "victims": {"number_of_victims": 1},
            "event_family": "homicidio",
            "event_subtype": "simples",
            "homicide_dynamic": {"method": "Arma de fogo"},
        },
        scoring=CaseScoring(),
    )
    return base.model_copy(update=overrides)


def test_validate_labeled_case():
    fixture = ExtractionFixture(meta=ExtractionFixtureMeta(), cases=[_sample_case()])
    result = validate_extraction_fixture(fixture)
    assert result.valid is True
    assert result.labeled_count == 1


def test_validate_pending_with_expected_fails():
    case = _sample_case(label_status="pending")
    fixture = ExtractionFixture(meta=ExtractionFixtureMeta(), cases=[case])
    result = validate_extraction_fixture(fixture)
    assert any("pending case should have expected=null" in i.message for i in result.issues)


def test_score_perfect_match():
    case = _sample_case()
    passed, score, field_results, diff = score_case(case, case.expected)
    assert passed is True
    assert score == 1.0
    assert diff == {}
    assert all(field_results.values())


def test_score_field_mismatch():
    case = _sample_case()
    actual = {**case.expected, "location_info": {"city": "Niterói", "state": "RJ"}}
    passed, score, field_results, diff = score_case(case, actual)
    assert passed is False
    assert score < 1.0
    assert field_results["location_info.city"] is False
    assert "location_info.city" in diff
