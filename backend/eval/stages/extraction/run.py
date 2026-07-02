"""Run extraction eval against a labeled fixture."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.schemas_extraction import (
    ExtractionCaseResult,
    ExtractionFixture,
    ExtractionRunMeta,
    ExtractionRunReport,
    utc_now_iso,
)
from eval.stages.extraction.score import event_to_dict, score_case, score_extraction_results
from eval.stages.extraction.validate import labeled_cases, validate_fixture
from eval.variants import ExtractionVariant, load_extraction_variant


def _resolve_model(variant: ExtractionVariant) -> str:
    from app.config import get_settings

    if variant.extraction_model:
        return variant.extraction_model
    return get_settings().extraction_model


def _run_one_case(case, variant: ExtractionVariant) -> ExtractionCaseResult:
    from app.config import get_settings
    from app.services.extraction import extract_event_from_content

    settings = get_settings()
    content = case.input.content
    if len(content) > settings.extraction_max_chars:
        content = content[: settings.extraction_max_chars]

    metadata = case.input.metadata.model_dump(exclude_none=True)
    start = time.perf_counter()
    try:
        event = extract_event_from_content(
            content,
            metadata,
            model_id=variant.extraction_model,
            system_prompt=variant.system_prompt,
        )
        actual = event_to_dict(event)
        passed, score, field_results, diff = score_case(case, actual)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ExtractionCaseResult(
            id=case.id,
            passed=passed,
            score=score,
            field_results=field_results,
            diff=diff,
            tags=case.tags,
            headline=case.input.metadata.headline,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ExtractionCaseResult(
            id=case.id,
            passed=False,
            score=0.0,
            tags=case.tags,
            headline=case.input.metadata.headline,
            latency_ms=latency_ms,
            error=str(e),
        )


async def run_extraction_eval(
    fixture: ExtractionFixture,
    *,
    variant_name: str = "baseline",
    concurrency: int = 3,
    limit: int | None = None,
    case_ids: set[str] | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
    fixture_path: str = "",
) -> ExtractionRunReport:
    validation = validate_fixture(fixture)
    if not validation.valid:
        raise ValueError("Fixture validation failed; fix issues before running eval")

    cases = labeled_cases(fixture)
    if case_ids:
        cases = [c for c in cases if c.id in case_ids]
    if limit is not None:
        cases = cases[:limit]

    variant = load_extraction_variant(variant_name)
    model = _resolve_model(variant)

    if dry_run:
        summary = score_extraction_results([])
        summary.total = len(cases)
        return ExtractionRunReport(
            meta=ExtractionRunMeta(
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

    summary = score_extraction_results(results)
    return ExtractionRunReport(
        meta=ExtractionRunMeta(
            variant=variant_name,
            model=model,
            fixture=fixture_path,
            run_at=utc_now_iso(),
        ),
        summary=summary,
        cases=results,
    )


def write_report(report: ExtractionRunReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


def default_output_path(variant: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parents[2] / "results" / f"extraction-{variant}-{ts}.json"


def print_report(report: ExtractionRunReport) -> None:
    s = report.summary
    print(f"\n=== RUN: extraction ({report.meta.variant}) ===")
    print(f"  model: {report.meta.model}")
    print(f"  fixture: {report.meta.fixture}")
    if report.meta.dry_run:
        print(f"  dry-run: {s.total} labeled cases would run")
        return

    print(f"  passed: {s.passed}/{s.total} ({_pct(s.mean_score)})")
    if s.errors:
        print(f"  errors: {s.errors}")

    if s.by_field:
        print("  by field:")
        for field_path, stats in s.by_field.items():
            print(f"    {field_path}: {stats['passed']}/{stats['total']} ({_pct(stats['accuracy'])})")

    failures = [r for r in report.cases if not r.passed and r.error is None]
    if failures:
        print(f"\n  field failures ({len(failures)}):")
        for r in failures[:8]:
            headline = (r.headline or "")[:60]
            print(f"    - {r.id} score={r.score:.2f} \"{headline}\"")
            for field_path, detail in list(r.diff.items())[:3]:
                print(f"        {field_path}: expected={detail.get('expected')!r} actual={detail.get('actual')!r}")

    if s.errors:
        print(f"\n  case errors ({s.errors}):")
        for r in report.cases:
            if r.error:
                print(f"    - {r.id}: {r.error[:160]}")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
