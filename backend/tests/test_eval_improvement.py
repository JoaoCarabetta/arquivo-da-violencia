"""Tests for eval improvement loop helpers."""

import json
import sqlite3

from eval.compare import compare_case_results, compare_generic_reports
from eval.improvement.detect import parse_stages
from eval.improvement.review import build_review_markdown, emit_review_for_output
from eval.improvement.schemas import AnomalyCandidate, CandidateBundle, VerificationResult


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


def _make_snapshot_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE unique_event (id INTEGER PRIMARY KEY, title TEXT, city TEXT, "
        "state TEXT, event_date TEXT, victims_summary TEXT, source_count INTEGER)"
    )
    conn.execute(
        "INSERT INTO unique_event VALUES (9722, 'Tiroteio na Aarão Reis', "
        "'Belo Horizonte', 'MG', '2026-07-05', '1 morto', 2)"
    )
    conn.execute(
        "INSERT INTO unique_event VALUES (9723, 'Homem morto em BH', "
        "'Belo Horizonte', 'MG', '2026-07-05', '1 morto', 1)"
    )
    conn.commit()
    conn.close()


def test_build_review_markdown_dedup_match(tmp_path):
    db_path = tmp_path / "snap.db"
    _make_snapshot_db(db_path)
    candidate = AnomalyCandidate(
        stage="dedup-match",
        candidate_id="prod-dedup_match-9722-9723",
        signal="title_similarity",
        reason="Near-duplicate unique events",
        prod_snapshot={"id_a": 9722, "id_b": 9723, "similarity": 0.91},
    )
    md = build_review_markdown(
        candidates=[candidate],
        db_path=db_path,
        title="Test review",
    )
    assert "## Quick list" in md
    assert "prod-dedup_match-9722-9723" in md
    assert "Belo Horizonte" in md
    assert "Tiroteio na Aarão Reis" in md
    assert "## How to respond" in md


def test_emit_review_for_output_candidates(tmp_path):
    db_path = tmp_path / "snap.db"
    _make_snapshot_db(db_path)
    candidates_path = tmp_path / "candidates.json"
    bundle = CandidateBundle(
        meta={"date_from": "2026-07-03", "date_to": "2026-07-07"},
        candidates=[
            AnomalyCandidate(
                stage="dedup-match",
                candidate_id="prod-dedup_match-9722-9723",
                signal="title_similarity",
                reason="Near-duplicate unique events",
                prod_snapshot={"id_a": 9722, "id_b": 9723},
            )
        ],
    )
    candidates_path.write_text(bundle.model_dump_json(indent=2))
    review_path, count = emit_review_for_output(candidates_path, db_path=db_path)
    assert count == 1
    assert review_path.name == "candidates-review.md"
    assert "Quick list" in review_path.read_text()


def test_emit_review_for_output_verified(tmp_path):
    candidate = AnomalyCandidate(
        stage="dedup-match",
        candidate_id="prod-dedup_match-9722-9723",
        signal="title_similarity",
        reason="Near-duplicate unique events",
        prod_snapshot={"id_a": 9722, "id_b": 9723},
    )
    verified_path = tmp_path / "verified.json"
    verified_path.write_text(
        json.dumps(
            {
                "meta": {},
                "results": [
                    VerificationResult(
                        candidate_id=candidate.candidate_id,
                        stage=candidate.stage,
                        verified=True,
                        notes="Re-run confirms duplicate",
                        candidate=candidate,
                    ).model_dump()
                ],
            }
        )
    )
    review_path, count = emit_review_for_output(verified_path)
    assert count == 1
    assert review_path.name == "verified-review.md"
    text = review_path.read_text()
    assert "verified ✓" in text
    assert "Re-run confirms duplicate" in text
