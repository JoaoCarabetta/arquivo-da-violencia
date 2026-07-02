"""Score classification eval results."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from eval.schemas import CaseResult, RunSummary


def score_case_results(results: Iterable[CaseResult]) -> RunSummary:
    results_list = list(results)
    total = len(results_list)
    passed = sum(1 for r in results_list if r.passed)
    failed = sum(1 for r in results_list if not r.passed and r.error is None)
    errors = sum(1 for r in results_list if r.error is not None)

    tp = fp = fn = 0
    for r in results_list:
        if r.error is not None or r.expected is None or r.actual is None:
            continue
        if r.expected and r.actual:
            tp += 1
        elif not r.expected and r.actual:
            fp += 1
        elif r.expected and not r.actual:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is not None and recall is not None and (precision + recall):
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None

    accuracy = passed / total if total else None
    by_tag = _by_tag_accuracy(results_list)

    return RunSummary(
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


def _by_tag_accuracy(results: list[CaseResult]) -> dict[str, dict]:
    tag_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in results:
        for tag in r.tags:
            tag_stats[tag]["total"] += 1
            if r.passed:
                tag_stats[tag]["passed"] += 1

    by_tag: dict[str, dict] = {}
    for tag, stats in sorted(tag_stats.items()):
        total = stats["total"]
        passed = stats["passed"]
        by_tag[tag] = {
            "total": total,
            "passed": passed,
            "accuracy": passed / total if total else None,
        }
    return by_tag
