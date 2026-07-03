"""Field-level scoring for enrichment eval (flat fields on EnrichmentResult)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from eval.schemas_enrichment import (
    EnrichmentCase,
    EnrichmentCaseResult,
    EnrichmentRunSummary,
)


def _normalize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = unicodedata.normalize("NFKD", value.strip().lower())
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = re.sub(r"\s+", " ", text)
        return text
    return value


def score_case(case: EnrichmentCase, actual: dict[str, Any]) -> tuple[bool, float, dict[str, bool], dict]:
    expected = case.expected or {}
    field_results: dict[str, bool] = {}
    diff: dict[str, dict[str, Any]] = {}

    for field in case.scoring.required_fields:
        exp_val = expected.get(field)
        act_val = actual.get(field)
        match = _normalize(exp_val) == _normalize(act_val)
        field_results[field] = match
        if not match:
            diff[field] = {"expected": exp_val, "actual": act_val}

    if not field_results:
        return True, 1.0, field_results, diff

    passed_count = sum(1 for ok in field_results.values() if ok)
    score = passed_count / len(field_results)
    return passed_count == len(field_results), score, field_results, diff


def score_enrichment_results(results: list[EnrichmentCaseResult]) -> EnrichmentRunSummary:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed and r.error is None)
    errors = sum(1 for r in results if r.error is not None)
    scored = [r for r in results if r.error is None]
    mean_score = sum(r.score for r in scored) / len(scored) if scored else None

    by_tag: dict[str, dict[str, Any]] = {}
    for result in results:
        for tag in result.tags:
            stats = by_tag.setdefault(tag, {"total": 0, "passed": 0})
            stats["total"] += 1
            if result.passed:
                stats["passed"] += 1
    for stats in by_tag.values():
        stats["accuracy"] = stats["passed"] / stats["total"] if stats["total"] else None

    by_field: dict[str, dict[str, Any]] = {}
    for result in results:
        if result.error:
            continue
        for field, ok in result.field_results.items():
            stats = by_field.setdefault(field, {"total": 0, "passed": 0})
            stats["total"] += 1
            if ok:
                stats["passed"] += 1
    for stats in by_field.values():
        stats["accuracy"] = stats["passed"] / stats["total"] if stats["total"] else None

    return EnrichmentRunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        mean_score=mean_score,
        by_tag=by_tag,
        by_field=by_field,
    )
