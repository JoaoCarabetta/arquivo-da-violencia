"""Run dedup-cluster eval against a labeled fixture.

Calls the production `llm_cluster_events` with RawEvent objects built from
fixture data (no DB access) and scores the returned partition.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.schemas_dedup import (
    DedupClusterCaseResult,
    DedupClusterFixture,
    DedupClusterRunMeta,
    DedupClusterRunReport,
    utc_now_iso,
)
from eval.stages.dedup_cluster.score import score_case_results, score_clusters
from eval.stages.dedup_cluster.validate import labeled_cases, validate_fixture
from eval.stages.dedup_match.run import raw_event_from_data
from eval.variants import StageVariant, load_stage_variant

MODEL_KEYS = ("dedup_model", "extraction_model")


def _resolve_model(variant: StageVariant) -> str:
    from app.config import get_settings

    return variant.model or get_settings().dedup_model


def _run_one_case(case, variant: StageVariant) -> DedupClusterCaseResult:
    from app.services.enrichment import cluster_within_group, llm_cluster_events

    events = [raw_event_from_data(e) for e in case.input.events]
    id_to_index = {e.id: i + 1 for i, e in enumerate(events)}

    start = time.perf_counter()
    try:
        clusters = cluster_within_group(events)
        latency_ms = int((time.perf_counter() - start) * 1000)

        actual = [sorted(id_to_index[e.id] for e in cluster) for cluster in clusters]
        expected = [sorted(c) for c in case.expected.clusters]

        exact, precision, recall, f1 = score_clusters(expected, actual)
        return DedupClusterCaseResult(
            id=case.id,
            passed=exact,
            pairwise_precision=precision,
            pairwise_recall=recall,
            pairwise_f1=f1,
            expected_clusters=expected,
            actual_clusters=actual,
            tags=case.tags,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return DedupClusterCaseResult(
            id=case.id,
            passed=False,
            expected_clusters=case.expected.clusters if case.expected else [],
            tags=case.tags,
            latency_ms=latency_ms,
            error=str(e),
        )


async def run_dedup_cluster_eval(
    fixture: DedupClusterFixture,
    *,
    variant_name: str = "baseline",
    concurrency: int = 4,
    limit: int | None = None,
    case_ids: set[str] | None = None,
    fail_fast: bool = False,
    dry_run: bool = False,
    fixture_path: str = "",
) -> DedupClusterRunReport:
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
        return DedupClusterRunReport(
            meta=DedupClusterRunMeta(
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
    return DedupClusterRunReport(
        meta=DedupClusterRunMeta(
            variant=variant_name,
            model=model,
            fixture=fixture_path,
            run_at=utc_now_iso(),
        ),
        summary=summary,
        cases=results,
    )


def write_report(report: DedupClusterRunReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


def default_output_path(variant: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(__file__).resolve().parents[2] / "results" / f"dedup-cluster-{variant}-{ts}.json"


def print_report(report: DedupClusterRunReport) -> None:
    s = report.summary
    print(f"\n=== RUN: dedup_cluster ({report.meta.variant}) ===")
    print(f"  model: {report.meta.model}")
    print(f"  fixture: {report.meta.fixture}")
    if report.meta.dry_run:
        print(f"  dry-run: {s.total} labeled cases would run")
        return

    print(f"  exact partition: {s.passed}/{s.total} ({_pct(s.exact_match_rate)})")
    print(f"  mean pairwise f1: {_pct(s.mean_pairwise_f1)}")
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
                f"    - {r.id} f1={r.pairwise_f1:.2f}: "
                f"expected={r.expected_clusters} actual={r.actual_clusters}"
            )

    if s.errors:
        print(f"\n  case errors ({s.errors}):")
        for r in report.cases:
            if r.error:
                print(f"    - {r.id}: {r.error[:160]}")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
