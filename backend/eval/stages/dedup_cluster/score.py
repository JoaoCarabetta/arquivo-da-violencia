"""Score dedup-cluster eval results with pairwise precision/recall over same-cluster pairs."""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Iterable

from eval.schemas_dedup import DedupClusterCaseResult, DedupClusterRunSummary


def _pairs(clusters: list[list[int]]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for cluster in clusters:
        for a, b in combinations(sorted(cluster), 2):
            pairs.add((a, b))
    return pairs


def _canonical(clusters: list[list[int]]) -> set[frozenset[int]]:
    return {frozenset(c) for c in clusters if c}


def score_clusters(
    expected: list[list[int]], actual: list[list[int]]
) -> tuple[bool, float | None, float | None, float | None]:
    """Return (exact_match, pairwise_precision, pairwise_recall, pairwise_f1).

    When neither partition contains any same-cluster pair (all singletons),
    precision/recall are defined as 1.0.
    """
    exact = _canonical(expected) == _canonical(actual)
    exp_pairs = _pairs(expected)
    act_pairs = _pairs(actual)

    if not exp_pairs and not act_pairs:
        return exact, 1.0, 1.0, 1.0

    tp = len(exp_pairs & act_pairs)
    precision = tp / len(act_pairs) if act_pairs else (1.0 if not exp_pairs else 0.0)
    recall = tp / len(exp_pairs) if exp_pairs else (1.0 if not act_pairs else 0.0)
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return exact, precision, recall, f1


def score_case_results(results: Iterable[DedupClusterCaseResult]) -> DedupClusterRunSummary:
    results_list = list(results)
    total = len(results_list)
    passed = sum(1 for r in results_list if r.passed)
    failed = sum(1 for r in results_list if not r.passed and r.error is None)
    errors = sum(1 for r in results_list if r.error is not None)

    scored = [r for r in results_list if r.error is None and r.pairwise_f1 is not None]
    mean_pairwise_f1 = sum(r.pairwise_f1 for r in scored) / len(scored) if scored else None
    exact_match_rate = passed / total if total else None

    tag_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in results_list:
        for tag in r.tags:
            tag_stats[tag]["total"] += 1
            if r.passed:
                tag_stats[tag]["passed"] += 1
    by_tag = {
        tag: {
            "total": stats["total"],
            "passed": stats["passed"],
            "accuracy": stats["passed"] / stats["total"] if stats["total"] else None,
        }
        for tag, stats in sorted(tag_stats.items())
    }

    return DedupClusterRunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        exact_match_rate=exact_match_rate,
        mean_pairwise_f1=mean_pairwise_f1,
        by_tag=by_tag,
    )
