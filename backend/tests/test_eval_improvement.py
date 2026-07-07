"""Tests for eval improvement loop helpers."""

from eval.compare import compare_case_results, compare_generic_reports
from eval.improvement.detect import parse_stages


def test_parse_stages_all():
    assert parse_stages("all") == [
        "classification",
        "content-gate",
        "extraction",
        "dedup-match",
        "dedup-cluster",
        "enrichment",
    ]


def test_parse_stages_single():
    assert parse_stages("dedup-match") == ["dedup-match"]


def test_compare_case_results_regression():
    baseline = [
        {"id": "a", "passed": True, "actual": True},
        {"id": "b", "passed": True, "actual": False},
    ]
    candidate = [
        {"id": "a", "passed": False, "actual": False},
        {"id": "b", "passed": True, "actual": False},
    ]
    result = compare_case_results(baseline, candidate)
    assert len(result["regressions"]) == 1
    assert result["regressions"][0]["id"] == "a"
    assert result["unchanged_pass"] == 1


def test_compare_generic_reports(tmp_path):
    baseline = {
        "meta": {"variant": "baseline"},
        "cases": [{"id": "x", "passed": True, "actual": 1}],
    }
    candidate = {
        "meta": {"variant": "trial"},
        "cases": [{"id": "x", "passed": False, "actual": 0}],
    }
    b_path = tmp_path / "b.json"
    c_path = tmp_path / "c.json"
    b_path.write_text(__import__("json").dumps(baseline))
    c_path.write_text(__import__("json").dumps(candidate))
    result = compare_generic_reports(b_path, c_path)
    assert result["baseline"]["variant"] == "baseline"
    assert result["candidate"]["variant"] == "trial"
    assert len(result["regressions"]) == 1
