"""Run classification eval against a labeled fixture."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.schemas import CaseResult, RunMeta, RunReport, utc_now_iso
from eval.stages.classification.score import score_case_results
from eval.stages.classification.validate import labeled_cases, validate_fixture
from eval.variants import ClassificationVariant, load_classification_variant


def _resolve_model(variant: ClassificationVariant) -> str:
    from app.config import get_settings

    if variant.selection_model:
        return variant.selection_model
    return get_settings().selection_model


def _run_one_case(
    case,
    variant: ClassificationVariant,
) -> CaseResult:
    from app.config import get_settings
    from app.services.classification import classify_headline

    start = time.perf_counter()
    try:
        result = classify_headline(
            case.input.headline,
            system_prompt=variant.system_prompt,
            model=variant.selection_model,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        expected = case.expected.is_violent_death
        actual = result.is_violent_death
        return CaseResult(
            id=case.id,
            passed=expected == actual,
            expected=expected,
            actual=actual,
            confidence=result.confidence,
            reasoning=result.reasoning,
            headline=case.input.headline,
            tags=case.tags,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        expected = case.expected.is_violent_death if case.expected else None
        return CaseResult(
            id=case.id,
            passed=False,
            expected=expected,
            actual=None,
            headline=case.input.headline,
            tags=case.tags,
            latency_ms=latency_ms,
            error=str(e),
        )


async def run_classification_eval(
    fixture,
    *,
    variant_name: str = "baseline",
    concurrency: int = 5,
    limit: int | None = None,
    case_ids: set[str] | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
    fixture_path: str = "",
) -> RunReport:
    validation = validate_fixture(fixture)
    if not validation.valid:
        raise ValueError("Fixture validation failed; fix issues before running eval")

    cases = labeled_cases(fixture)
    if case_ids:
        cases = [c for c in cases if c.id in case_ids]
    if limit is not None:
        cases = cases[:limit]

    variant = load_classification_variant(variant_name)
    model = _resolve_model(variant)

    if dry_run:
        summary = score_case_results([])
        summary.total = len(cases)
        return RunReport(
            meta=RunMeta(
                variant=variant_name,
                model=model,
                fixture=fixture_path,
                run_at=utc_now_iso(),
                dry_run=True,
            ),
            summary=summary,
            cases=[],
        )

    from app.config import get_settings

    if not get_settings().gemini_api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    sem = asyncio.Semaphore(concurrency)

    async def worker(case):
        async with sem:
            return await asyncio.to_thread(_run_one_case, case, variant)

    tasks = [worker(case) for case in cases]
    if fail_fast:
        results = []
        for task in tasks:
            result = await task
            results.append(result)
            if not result.passed:
                break
    else:
        results = list(await asyncio.gather(*tasks))

    summary = score_case_results(results)
    return RunReport(
        meta=RunMeta(
            variant=variant_name,
            model=model,
            fixture=fixture_path,
            run_at=utc_now_iso(),
        ),
        summary=summary,
        cases=results,
    )


def write_report(report: RunReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


def default_output_path(variant: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parents[2] / "results" / f"classification-{variant}-{ts}.json"


def print_report(report: RunReport) -> None:
    s = report.summary
    print(f"\n=== RUN: classification ({report.meta.variant}) ===")
    print(f"  model: {report.meta.model}")
    print(f"  fixture: {report.meta.fixture}")
    if report.meta.dry_run:
        print(f"  dry-run: {s.total} labeled cases would run")
        return

    print(f"  passed: {s.passed}/{s.total} ({_pct(s.accuracy)})")
    print(f"  precision: {_pct(s.precision)}, recall: {_pct(s.recall)}, f1: {_pct(s.f1)}")
    if s.errors:
        print(f"  errors: {s.errors}")

    if s.by_tag:
        print("  by tag:")
        for tag, stats in s.by_tag.items():
            print(f"    {tag}: {stats['passed']}/{stats['total']} ({_pct(stats['accuracy'])})")

    false_positives = [
        r for r in report.cases if r.error is None and r.expected is False and r.actual is True
    ]
    false_negatives = [
        r for r in report.cases if r.error is None and r.expected is True and r.actual is False
    ]

    if false_positives:
        print(f"\n  false positives ({len(false_positives)}):")
        for r in false_positives[:10]:
            print(f"    - {r.id}: \"{r.headline[:70] if r.headline else ''}\"")
            if r.reasoning:
                print(f"      {r.reasoning[:120]}")

    if false_negatives:
        print(f"\n  false negatives ({len(false_negatives)}):")
        for r in false_negatives[:10]:
            print(f"    - {r.id}: \"{r.headline[:70] if r.headline else ''}\"")
            if r.reasoning:
                print(f"      {r.reasoning[:120]}")

    if s.errors:
        print(f"\n  case errors ({s.errors}):")
        for r in report.cases:
            if r.error:
                print(f"    - {r.id}: {r.error}")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
