"""Tests for eval improvement loop helpers."""

import json
import sqlite3

from eval.compare import compare_case_results, compare_generic_reports
from eval.improvement.detect import parse_stages
from eval.improvement.diagnose import build_diagnosis
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
    assert "## Fix recommendations (approve these)" in md
    assert "prod-dedup_match-9722-9723" in md
    assert "Belo Horizonte" in md
    assert "## Candidate appendix" in md


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
    review_path, count, cluster_count = emit_review_for_output(candidates_path, db_path=db_path)
    assert count == 1
    assert cluster_count >= 1
    assert review_path.name == "candidates-review.md"
    assert "Fix recommendations" in review_path.read_text()


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
    review_path, count, cluster_count = emit_review_for_output(verified_path)
    assert count == 1
    assert cluster_count >= 1
    assert review_path.name == "verified-review.md"
    text = review_path.read_text()
    assert "Fix recommendations" in text
    assert "Re-run confirms duplicate" in text


def test_build_diagnosis_clusters_by_solution_not_incident():
    """Three pairs sharing UEs 9722/9723/9730 → one solution cluster with one affected incident."""
    candidates = [
        AnomalyCandidate(
            stage="dedup-match",
            candidate_id=f"prod-dedup_match-{a}-{b}",
            signal="near_duplicate_unique_events",
            reason=f"Pair {a}-{b}",
            prod_snapshot={
                "id_a": a,
                "id_b": b,
                "signal": "victim_name",
                "city": "Belo Horizonte",
                "event_date": "2026-07-03",
                "similarity": 1.0,
            },
        )
        for a, b in [(9722, 9723), (9722, 9730), (9723, 9730)]
    ]
    report = build_diagnosis(candidates)
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.total_count == 3
    assert len(cluster.affected) == 1
    assert set(cluster.affected[0].unique_event_ids) == {9722, 9723, 9730}
    assert cluster.affected[0].pair_count == 3
    assert "incidents" in cluster.evidence


def test_build_diagnosis_merges_same_solution_across_cities():
    """Same victim_name dedup problem in two cities → one fix cluster, two affected incidents."""
    candidates = [
        AnomalyCandidate(
            stage="dedup-match",
            candidate_id="prod-dedup_match-1-2",
            signal="near_duplicate_unique_events",
            reason="pair",
            prod_snapshot={
                "id_a": 1,
                "id_b": 2,
                "signal": "victim_name",
                "city": "Salvador",
                "event_date": "2026-07-03",
            },
        ),
        AnomalyCandidate(
            stage="dedup-match",
            candidate_id="prod-dedup_match-3-4",
            signal="near_duplicate_unique_events",
            reason="pair",
            prod_snapshot={
                "id_a": 3,
                "id_b": 4,
                "signal": "victim_name",
                "city": "Belo Horizonte",
                "event_date": "2026-07-03",
            },
        ),
    ]
    report = build_diagnosis(candidates)
    assert len(report.clusters) == 1
    assert len(report.clusters[0].affected) == 2
    assert report.clusters[0].evidence.startswith("2 incidents")


def test_build_diagnosis_includes_fix_recommendations():
    candidate = AnomalyCandidate(
        stage="dedup-cluster",
        candidate_id="prod-dedup_cluster-1-2",
        signal="pending_overlap_cluster",
        reason="2 pending events overlap",
        prod_snapshot={"city": "Cuiabá", "event_date": "2026-07-07", "raw_event_ids": [1, 2]},
        input={"raw_event_ids": [1, 2]},
    )
    report = build_diagnosis([candidate])
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert cluster.change_type == "ops"
    assert "process_pending_deduplication" in cluster.recommended_change
    assert any("enrichment.py" in t for t in cluster.change_targets)


def test_review_markdown_includes_diagnosis_section(tmp_path):
    db_path = tmp_path / "snap.db"
    _make_snapshot_db(db_path)
    candidate = AnomalyCandidate(
        stage="dedup-match",
        candidate_id="prod-dedup_match-9722-9723",
        signal="near_duplicate_unique_events",
        reason="Near-duplicate unique events",
        prod_snapshot={
            "id_a": 9722,
            "id_b": 9723,
            "signal": "victim_name",
            "city": "Belo Horizonte",
            "event_date": "2026-07-03",
        },
    )
    md = build_review_markdown(candidates=[candidate], db_path=db_path)
    assert "## Fix recommendations (approve these)" in md
    assert "**Problem:**" in md
    assert "**Solution:**" in md
    assert "**What will be affected:**" in md
    assert "## Candidate appendix" in md
