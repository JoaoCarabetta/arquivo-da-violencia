"""Run dedup-match eval against a labeled fixture.

Calls the production `llm_match_to_unique_event` with RawEvent/UniqueEvent
objects built from fixture data (no DB access).
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.schemas_dedup import (
    DedupMatchCaseResult,
    DedupMatchFixture,
    DedupMatchRunMeta,
    DedupMatchRunReport,
    RawEventData,
    UniqueEventData,
    utc_now_iso,
)
from eval.stages.dedup_match.score import score_case_results
from eval.stages.dedup_match.validate import labeled_cases, validate_fixture
from eval.variants import StageVariant, load_stage_variant

MODEL_KEYS = ("dedup_model", "extraction_model")


def _resolve_model(variant: StageVariant) -> str:
    from app.config import get_settings

    return variant.model or get_settings().dedup_model


def _parse_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def raw_event_from_data(data: RawEventData):
    from app.models import RawEvent

    extraction_data = None
    if data.victim_names:
        extraction_data = {
            "victims": {
                "identifiable_victims": [{"name": name} for name in data.victim_names]
            }
        }
    return RawEvent(
        id=data.id,
        title=data.title,
        event_date=_parse_date(data.event_date),
        city=data.city,
        state=data.state,
        neighborhood=data.neighborhood,
        homicide_type=data.homicide_type,
        chronological_description=data.chronological_description,
        extraction_data=extraction_data,
        extraction_success=True,
    )


def unique_event_from_data(data: UniqueEventData):
    from app.models import UniqueEvent

    return UniqueEvent(
        id=data.id,
        title=data.title,
        event_date=_parse_date(data.event_date),
        city=data.city,
        state=data.state,
        neighborhood=data.neighborhood,
        homicide_type=data.homicide_type,
        chronological_description=data.chronological_description,
        victims_summary=data.victims_summary,
        victim_count=data.victim_count,
        source_count=data.source_count,
    )


def _run_one_case(case, variant: StageVariant) -> DedupMatchCaseResult:
    from app.services.enrichment import llm_match_to_unique_event

    raw_event = raw_event_from_data(case.input.raw_event)
    candidates = [unique_event_from_data(c) for c in case.input.candidates]

    start = time.perf_counter()
    try:
        matched, confidence, reasoning = llm_match_to_unique_event(
            raw_event,
            candidates,
            model=variant.model,
            system_prompt=variant.system_prompt,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        if reasoning.startswith("LLM error"):
            raise RuntimeError(reasoning)

        actual_match = matched is not None
        actual_id = matched.id if matched else None
        expected_match = case.expected.match
        expected_id = case.expected.unique_event_id

        if expected_match:
            passed = actual_match and actual_id == expected_id
        else:
            passed = not actual_match

        return DedupMatchCaseResult(
            id=case.id,
            passed=passed,
            expected_match=expected_match,
            actual_match=actual_match,
            expected_id=expected_id,
            actual_id=actual_id,
            confidence=confidence,
            reasoning=reasoning,
            tags=case.tags,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DedupMatchCaseResult(
            id=case.id,
            passed=False,
            expected_match=case.expected.match if case.expected else None,
            expected_id=case.expected.unique_event_id if case.expected else None,
            tags=case.tags,
            latency_ms=latency_ms,
            error=str(e),
        )


async def run_dedup_match_eval(
    fixture: DedupMatchFixture,
    *,
    variant_name: str = "baseline",
    concurrency: int = 4,
    limit: int | None = None,
    case_ids: set[str] | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
    fixture_path: str = "",
) -> DedupMatchRunReport:
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
        summary = score_case_results([])
        summary.total = len(cases)
        return DedupMatchRunReport(
            meta=DedupMatchRunMeta(
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

    summary = score_case_results(results)
    return DedupMatchRunReport(
        meta=DedupMatchRunMeta(
            variant=variant_name,
            model=model,
            fixture=fixture_path,
            run_at=utc_now_iso(),
        ),
        summary=summary,
        cases=results,
    )


def write_report(report: DedupMatchRunReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


def default_output_path(variant: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parents[2] / "results" / f"dedup-match-{variant}-{ts}.json"


def print_report(report: DedupMatchRunReport) -> None:
    s = report.summary
    print(f"\n=== RUN: dedup_match ({report.meta.variant}) ===")
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

    failures = [r for r in report.cases if not r.passed and r.error is None]
    if failures:
        print(f"\n  failures ({len(failures)}):")
        for r in failures[:10]:
            print(
                f"    - {r.id}: expected match={r.expected_match} id={r.expected_id}, "
                f"got match={r.actual_match} id={r.actual_id} (conf={r.confidence})"
            )
            if r.reasoning:
                print(f"      {r.reasoning[:140]}")

    if s.errors:
        print(f"\n  case errors ({s.errors}):")
        for r in report.cases:
            if r.error:
                print(f"    - {r.id}: {r.error[:160]}")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
