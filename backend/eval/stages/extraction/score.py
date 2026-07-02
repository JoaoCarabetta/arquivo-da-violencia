"""Field-level scoring for extraction eval."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.services.extraction_schemas import ViolentDeathEvent

from eval.schemas_extraction import (
    ExtractionCase,
    ExtractionCaseResult,
    ExtractionRunSummary,
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


def _get_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def event_to_dict(event: ViolentDeathEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def score_case(case: ExtractionCase, actual: dict[str, Any]) -> tuple[bool, float, dict[str, bool], dict]:
    expected = case.expected or {}
    field_results: dict[str, bool] = {}
    diff: dict[str, dict[str, Any]] = {}

    for field_path in case.scoring.required_fields:
        exp_val = _get_path(expected, field_path)
        act_val = _get_path(actual, field_path)
        match = _normalize(exp_val) == _normalize(act_val)
        field_results[field_path] = match
        if not match:
            diff[field_path] = {"expected": exp_val, "actual": act_val}

    if not field_results:
        return True, 1.0, field_results, diff

    passed_count = sum(1 for ok in field_results.values() if ok)
    score = passed_count / len(field_results)
    passed = passed_count == len(field_results)
    return passed, score, field_results, diff


def score_extraction_results(results: list[ExtractionCaseResult]) -> ExtractionRunSummary:
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
    for tag, stats in by_tag.items():
        stats["accuracy"] = stats["passed"] / stats["total"] if stats["total"] else None

    by_field: dict[str, dict[str, Any]] = {}
    for result in results:
        if result.error:
            continue
        for field_path, ok in result.field_results.items():
            stats = by_field.setdefault(field_path, {"total": 0, "passed": 0})
            stats["total"] += 1
            if ok:
                stats["passed"] += 1
    for field_path, stats in by_field.items():
        stats["accuracy"] = stats["passed"] / stats["total"] if stats["total"] else None

    return ExtractionRunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        mean_score=mean_score,
        by_tag=by_tag,
        by_field=by_field,
    )
