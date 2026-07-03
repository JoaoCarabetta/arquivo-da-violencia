"""Score content-gate eval results (gate = is_violent_death AND is_single_incident)."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from eval.schemas_content_gate import ContentGateCaseResult, ContentGateRunSummary


def score_case_results(results: Iterable[ContentGateCaseResult]) -> ContentGateRunSummary:
    results_list = list(results)
    total = len(results_list)
    passed = sum(1 for r in results_list if r.passed)
    failed = sum(1 for r in results_list if not r.passed and r.error is None)
    errors = sum(1 for r in results_list if r.error is not None)

    tp = fp = fn = 0
    for r in results_list:
        if r.error is not None or r.expected_gate is None or r.actual_gate is None:
            continue
        if r.expected_gate and r.actual_gate:
            tp += 1
        elif not r.expected_gate and r.actual_gate:
            fp += 1
        elif r.expected_gate and not r.actual_gate:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is not None and recall is not None and (precision + recall):
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None

    accuracy = passed / total if total else None

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

    return ContentGateRunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        by_tag=by_tag,
    )
