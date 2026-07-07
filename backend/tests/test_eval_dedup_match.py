"""Tests for dedup-match eval fixtures (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from eval.schemas_dedup import load_dedup_match_fixture
from eval.stages.dedup_match.validate import validate_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "eval"
SEED = FIXTURES / "dedup_match_seed.json"
HARD = FIXTURES / "dedup_match_hard.json"


def test_validate_dedup_match_seed_fixture():
    fixture = load_dedup_match_fixture(json.loads(SEED.read_text()))
    result = validate_fixture(fixture)
    assert result.valid is True
    assert result.labeled_count == 2
    assert result.issues == []


def test_validate_dedup_match_hard_fixture():
    fixture = load_dedup_match_fixture(json.loads(HARD.read_text()))
    result = validate_fixture(fixture)
    assert result.valid is True
    assert result.labeled_count == 1


def test_dedup_match_seed_regression_cases():
    fixture = load_dedup_match_fixture(json.loads(SEED.read_text()))
    ids = {c.id for c in fixture.cases}
    assert "dm-pos-sao-jose-sc281-9843" in ids
    assert "dm-pos-confresa-daiany-9744" in ids
