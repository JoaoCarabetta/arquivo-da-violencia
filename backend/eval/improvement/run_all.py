"""Run the full 6-stage eval suite and aggregate the 100% gate."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = BACKEND_ROOT / "tests" / "fixtures" / "eval"
RESULTS_DIR = BACKEND_ROOT / "eval" / "results"

STAGE_FIXTURES: list[tuple[str, list[str]]] = [
    ("classification", ["classification_seed.json", "classification_hard.json"]),
    ("content-gate", ["content_gate_hard.json"]),
    ("extraction", ["extraction_hard.json", "taxonomy_regression.json"]),
    ("dedup-match", ["dedup_match_hard.json"]),
    ("dedup-cluster", ["dedup_cluster_seed.json"]),
    ("enrichment", ["enrichment_seed.json"]),
]


async def run_all_evals(
    *,
    variant: str = "baseline",
    concurrency: int = 4,
    dry_run: bool = False,
    output: Path | None = None,
) -> dict[str, Any]:
    stage_results: list[dict[str, Any]] = []
    all_passed = True
    total_passed = 0
    total_cases = 0

    for stage, fixture_names in STAGE_FIXTURES:
        for fixture_name in fixture_names:
            fixture_path = FIXTURES_DIR / fixture_name
            if not fixture_path.exists():
                stage_results.append({
                    "stage": stage,
                    "fixture": fixture_name,
                    "skipped": True,
                    "reason": "fixture not found",
                })
                continue

            report_path = RESULTS_DIR / f"run-all-{stage}-{fixture_name.replace('.json', '')}.json"
            summary = await _run_stage(
                stage,
                fixture_path,
                variant=variant,
                concurrency=concurrency,
                dry_run=dry_run,
                output=report_path,
            )
            stage_results.append(summary)
            if summary.get("skipped"):
                continue
            passed = summary.get("passed", 0)
            total = summary.get("total", 0)
            total_passed += passed
            total_cases += total
            if total > 0 and passed < total:
                all_passed = False

    payload = {
        "meta": {
            "command": "run-all",
            "run_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "variant": variant,
            "dry_run": dry_run,
        },
        "summary": {
            "all_passed": all_passed,
            "passed": total_passed,
            "total": total_cases,
            "accuracy": (total_passed / total_cases) if total_cases else None,
        },
        "stages": stage_results,
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    return payload


async def _run_stage(
    stage: str,
    fixture_path: Path,
    *,
    variant: str,
    concurrency: int,
    dry_run: bool,
    output: Path,
) -> dict[str, Any]:
    fixture_rel = f"tests/fixtures/eval/{fixture_path.name}"

    if stage == "classification":
        from eval.schemas import load_fixture
        from eval.stages.classification.run import run_classification_eval, write_report

        fixture = load_fixture(json.loads(fixture_path.read_text()))
        report = await run_classification_eval(
            fixture,
            variant_name=variant,
            concurrency=concurrency,
            dry_run=dry_run,
            fixture_path=str(fixture_path),
        )
        if not dry_run:
            write_report(report, output)
        return _summary_from_report(stage, fixture_path.name, report.summary.passed, report.summary.total, output)

    if stage == "extraction":
        from eval.schemas_extraction import load_extraction_fixture
        from eval.stages.extraction.run import run_extraction_eval, write_report

        fixture = load_extraction_fixture(json.loads(fixture_path.read_text()))
        report = await run_extraction_eval(
            fixture,
            variant_name=variant,
            concurrency=concurrency,
            dry_run=dry_run,
            fixture_path=str(fixture_path),
        )
        if not dry_run:
            write_report(report, output)
        return _summary_from_report(stage, fixture_path.name, report.summary.passed, report.summary.total, output)

    runners = {
        "content-gate": (
            "eval.schemas_content_gate",
            "load_content_gate_fixture",
            "eval.stages.content_gate.run",
            "run_content_gate_eval",
            "write_report",
        ),
        "dedup-match": (
            "eval.schemas_dedup",
            "load_dedup_match_fixture",
            "eval.stages.dedup_match.run",
            "run_dedup_match_eval",
            "write_report",
        ),
        "dedup-cluster": (
            "eval.schemas_dedup",
            "load_dedup_cluster_fixture",
            "eval.stages.dedup_cluster.run",
            "run_dedup_cluster_eval",
            "write_report",
        ),
        "enrichment": (
            "eval.schemas_enrichment",
            "load_enrichment_fixture",
            "eval.stages.enrichment.run",
            "run_enrichment_eval",
            "write_report",
        ),
    }

    if stage not in runners:
        return {"stage": stage, "fixture": fixture_path.name, "skipped": True, "reason": "unknown stage"}

    import importlib

    schemas_mod_name, loader_name, run_mod_name, runner_name, writer_name = runners[stage]
    schemas_mod = importlib.import_module(schemas_mod_name)
    run_mod = importlib.import_module(run_mod_name)
    loader = getattr(schemas_mod, loader_name)
    runner = getattr(run_mod, runner_name)
    writer = getattr(run_mod, writer_name)

    fixture = loader(json.loads(fixture_path.read_text()))
    report = await runner(
        fixture,
        variant_name=variant,
        concurrency=concurrency,
        dry_run=dry_run,
        fixture_path=str(fixture_path),
    )
    if not dry_run:
        writer(report, output)
    return _summary_from_report(stage, fixture_path.name, report.summary.passed, report.summary.total, output)


def _summary_from_report(
    stage: str,
    fixture_name: str,
    passed: int,
    total: int,
    report_path: Path,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "fixture": fixture_name,
        "passed": passed,
        "total": total,
        "accuracy": (passed / total) if total else None,
        "report": str(report_path.relative_to(BACKEND_ROOT)) if report_path.exists() else None,
    }


def print_run_all_summary(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"\n=== RUN-ALL: {summary['passed']}/{summary['total']} ({_pct(summary.get('accuracy'))}) ===")
    print(f"  all_passed: {summary['all_passed']}")
    for stage in payload.get("stages", []):
        if stage.get("skipped"):
            print(f"  {stage['stage']} / {stage['fixture']}: SKIPPED ({stage.get('reason')})")
        else:
            print(
                f"  {stage['stage']} / {stage['fixture']}: "
                f"{stage['passed']}/{stage['total']} ({_pct(stage.get('accuracy'))})"
            )


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
