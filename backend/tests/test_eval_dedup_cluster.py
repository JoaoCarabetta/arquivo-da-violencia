"""Tests for dedup-cluster eval fixture (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from eval.schemas_dedup import load_dedup_cluster_fixture
from eval.stages.dedup_cluster.validate import validate_fixture

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "eval" / "dedup_cluster_seed.json"


def test_validate_dedup_cluster_seed_fixture():
    fixture = load_dedup_cluster_fixture(json.loads(FIXTURE.read_text()))
    result = validate_fixture(fixture)
    assert result.valid is True
    assert result.labeled_count == 2
    assert result.issues == []


def test_dedup_cluster_seed_regression_cases():
    fixture = load_dedup_cluster_fixture(json.loads(FIXTURE.read_text()))
    ids = {c.id for c in fixture.cases}
    assert "dc-pos-confresa-daiany" in ids
    assert "dc-pos-sao-jose-sc281" in ids
