"""Run enrichment-synthesis eval against a labeled fixture.

Calls the production `synthesize_unique_event` plus `apply_raw_field_consensus`
with plain dicts (no DB access).
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.schemas_enrichment import (
    EnrichmentCaseResult,
    EnrichmentFixture,
    EnrichmentRunMeta,
    EnrichmentRunReport,
    utc_now_iso,
)
from eval.stages.enrichment.score import score_case, score_enrichment_results
from eval.stages.enrichment.validate import labeled_cases, validate_fixture
from eval.variants import StageVariant, load_stage_variant

MODEL_KEYS = ("enrichment_model", "extraction_model")


def _resolve_model(variant: StageVariant) -> str:
    from app.config import get_settings

    return variant.model or get_settings().enrichment_model


def _run_one_case(case, variant: StageVariant) -> EnrichmentCaseResult:
    from app.services.enrichment import apply_raw_field_consensus, synthesize_unique_event

    sources_info = [s.model_dump() for s in case.input.sources]
    start = time.perf_counter()
    try:
        result = synthesize_unique_event(
            case.input.current_state,
            sources_info,
            model=variant.model,
            system_prompt=variant.system_prompt,
        )
        consensus_rows = [
            type("RawRow", (), {"victim_count": s.victim_count, "city": s.city})()
            for s in case.input.sources
            if s.victim_count is not None or s.city
        ]
        if consensus_rows:
            result = apply_raw_field_consensus(result, consensus_rows)
        latency_ms = int((time.perf_counter() - start) * 1000)
        actual = result.model_dump(mode="json")
        passed, score, field_results, diff = score_case(case, actual)
        return EnrichmentCaseResult(
            id=case.id,
            passed=passed,
            score=score,
            field_results=field_results,
            diff=diff,
            tags=case.tags,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return EnrichmentCaseResult(
            id=case.id,
            passed=False,
            score=0.0,
            tags=case.tags,
            latency_ms=latency_ms,
            error=str(e),
        )


async def run_enrichment_eval(
    fixture: EnrichmentFixture,
    *,
    variant_name: str = "baseline",
    concurrency: int = 4,
    limit: int | None = None,
    case_ids: set[str] | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
    fixture_path: str = "",
) -> EnrichmentRunReport:
    validation = validate_fixture(fixture)
    if not validation.valid:
        raise ValueError("Fixture validation failed; fix issues before running eval")

    cases = labeled_cases(fixture)
    if case_ids:
        cases = [c for c in cases if c.id in case_ids]
    if limit is not None:
        cases = cases[:limit]

    variant = load_stage_variant(variant_name, model_keys=MODEL_KEYS)
    model = _resolve_model(variant)

    if dry_run:
        summary = score_enrichment_results([])
        summary.total = len(cases)
        return EnrichmentRunReport(
            meta=EnrichmentRunMeta(
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

    if not get_settings().openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

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

    summary = score_enrichment_results(results)
    return EnrichmentRunReport(
        meta=EnrichmentRunMeta(
            variant=variant_name,
            model=model,
            fixture=fixture_path,
            run_at=utc_now_iso(),
        ),
        summary=summary,
        cases=results,
    )


def write_report(report: EnrichmentRunReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


def default_output_path(variant: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parents[2] / "results" / f"enrichment-{variant}-{ts}.json"


def print_report(report: EnrichmentRunReport) -> None:
    s = report.summary
    print(f"\n=== RUN: enrichment ({report.meta.variant}) ===")
    print(f"  model: {report.meta.model}")
    print(f"  fixture: {report.meta.fixture}")
    if report.meta.dry_run:
        print(f"  dry-run: {s.total} labeled cases would run")
        return

    print(f"  passed: {s.passed}/{s.total} (mean score {_pct(s.mean_score)})")
    if s.errors:
        print(f"  errors: {s.errors}")

    if s.by_field:
        print("  by field:")
        for field, stats in s.by_field.items():
            print(f"    {field}: {stats['passed']}/{stats['total']} ({_pct(stats['accuracy'])})")

    failures = [r for r in report.cases if not r.passed and r.error is None]
    if failures:
        print(f"\n  field failures ({len(failures)}):")
        for r in failures[:8]:
            print(f"    - {r.id} score={r.score:.2f}")
            for field, detail in list(r.diff.items())[:3]:
                print(f"        {field}: expected={detail.get('expected')!r} actual={detail.get('actual')!r}")

    if s.errors:
        print(f"\n  case errors ({s.errors}):")
        for r in report.cases:
            if r.error:
                print(f"    - {r.id}: {r.error[:160]}")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
