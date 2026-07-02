"""Eval CLI dispatcher."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from eval.compare import compare_reports, load_report, print_compare
from eval.schemas import load_fixture
from eval.stages.classification.build import DEFAULT_OUT, build_fixture, write_fixture
from eval.stages.classification.validate import print_validation, validate_fixture

DEFAULT_SEED_FIXTURE = (
    BACKEND_ROOT / "tests" / "fixtures" / "eval" / "classification_seed.json"
)
DEFAULT_HARD_FIXTURE = (
    BACKEND_ROOT / "tests" / "fixtures" / "eval" / "classification_hard.json"
)


def _load_fixture_path(path: str):
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise SystemExit(f"Fixture not found: {fixture_path}")
    return load_fixture(json.loads(fixture_path.read_text())), str(fixture_path)


def cmd_validate(args: argparse.Namespace) -> None:
    fixture, fixture_path = _load_fixture_path(args.fixture)
    result = validate_fixture(fixture)
    print_validation(result, fixture_path)
    if not result.valid:
        raise SystemExit(1)


def cmd_build(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    merge_into = Path(args.merge_into) if args.merge_into else None
    fixture, added = build_fixture(db_path, args.n, args.seed, merge_into)
    out_path = Path(args.out)
    write_fixture(fixture, out_path)
    print(
        f"Wrote {out_path}: {added} new cases, "
        f"{fixture.meta.labeled_count} labeled, {fixture.meta.pending_count} pending"
    )


def cmd_generate_hard(args: argparse.Namespace) -> None:
    from eval.stages.classification.generate_hard import (
        GENERATOR_MODEL,
        write_hard_fixture,
    )

    out_path = Path(args.out)
    model = args.model or GENERATOR_MODEL
    path, true_count, false_count = write_hard_fixture(out_path, model=model)
    print(f"Wrote {path} (30 cases: {true_count} true, {false_count} false)")
    print(f"  generator: {model}")


async def cmd_run_async(args: argparse.Namespace) -> None:
    from eval.stages.classification.run import (
        default_output_path,
        print_report,
        run_classification_eval,
        write_report,
    )

    fixture, fixture_path = _load_fixture_path(args.fixture)
    case_ids = {s.strip() for s in args.ids.split(",") if s.strip()} if args.ids else None
    report = await run_classification_eval(
        fixture,
        variant_name=args.variant,
        concurrency=args.concurrency,
        limit=args.limit,
        case_ids=case_ids,
        fail_fast=args.fail_fast,
        dry_run=args.no_llm,
        fixture_path=fixture_path,
    )
    print_report(report)
    if args.output:
        output_path = Path(args.output)
    elif args.no_llm:
        output_path = None
    else:
        output_path = default_output_path(args.variant)
    if output_path:
        write_report(report, output_path)
        print(f"\nWrote {output_path}")


def cmd_run(args: argparse.Namespace) -> None:
    asyncio.run(cmd_run_async(args))


def cmd_compare(args: argparse.Namespace) -> None:
    baseline = load_report(Path(args.baseline))
    candidate = load_report(Path(args.candidate))
    result = compare_reports(baseline, candidate)
    print_compare(result)


def cmd_report(args: argparse.Namespace) -> None:
    from eval.stages.classification.run import print_report

    report = load_report(Path(args.run))
    print_report(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline eval harness")
    sub = parser.add_subparsers(dest="stage", required=True)

    cls = sub.add_parser("classification", help="Classification eval")
    cls_sub = cls.add_subparsers(dest="command", required=True)

    p_validate = cls_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_SEED_FIXTURE))
    p_validate.set_defaults(func=cmd_validate)

    p_build = cls_sub.add_parser("build", help="Sample pending cases from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=50)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(DEFAULT_OUT))
    p_build.add_argument("--merge-into", default=None, help="Append into existing fixture")
    p_build.set_defaults(func=cmd_build)

    p_generate = cls_sub.add_parser(
        "generate-hard",
        help="Generate adversarial cases with Gemini Pro (costs tokens)",
    )
    p_generate.add_argument("--out", default=str(DEFAULT_HARD_FIXTURE))
    p_generate.add_argument(
        "--model",
        default=None,
        help="Generator model (default: gemini-3.1-pro-preview)",
    )
    p_generate.set_defaults(func=cmd_generate_hard)

    p_run = cls_sub.add_parser("run", help="Run eval against labeled cases")
    p_run.add_argument("--fixture", default=str(DEFAULT_SEED_FIXTURE))
    p_run.add_argument("--variant", default="baseline")
    p_run.add_argument("--concurrency", type=int, default=5)
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--ids", default=None, help="Comma-separated case ids")
    p_run.add_argument("--output", default=None)
    p_run.add_argument("--fail-fast", action="store_true")
    p_run.add_argument("--no-llm", action="store_true", help="Validate only, no LLM calls")
    p_run.set_defaults(func=cmd_run)

    p_compare = cls_sub.add_parser("compare", help="Compare two run reports")
    p_compare.add_argument("--baseline", required=True)
    p_compare.add_argument("--candidate", required=True)
    p_compare.set_defaults(func=cmd_compare)

    p_report = cls_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
