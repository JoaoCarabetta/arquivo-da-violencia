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

from eval.compare import compare_generic_reports, compare_reports, load_report, print_compare
from eval.schemas import load_fixture
from eval.schemas_extraction import load_extraction_fixture
from eval.stages.classification.build import DEFAULT_OUT as CLS_DEFAULT_OUT
from eval.stages.classification.build import build_fixture as build_classification_fixture
from eval.stages.classification.build import write_fixture as write_classification_fixture
from eval.stages.classification.validate import print_validation as print_classification_validation
from eval.stages.classification.validate import validate_fixture as validate_classification_fixture
from eval.stages.extraction.build import DEFAULT_OUT as EXT_DEFAULT_OUT
from eval.stages.extraction.build import build_fixture as build_extraction_fixture
from eval.stages.extraction.build import write_fixture as write_extraction_fixture
from eval.stages.extraction.validate import print_validation as print_extraction_validation
from eval.stages.extraction.validate import validate_fixture as validate_extraction_fixture

FIXTURES_DIR = BACKEND_ROOT / "tests" / "fixtures" / "eval"
DEFAULT_CLS_SEED = FIXTURES_DIR / "classification_seed.json"
DEFAULT_CLS_HARD = FIXTURES_DIR / "classification_hard.json"
DEFAULT_EXT_SEED = FIXTURES_DIR / "extraction_seed.json"
DEFAULT_EXT_HARD = FIXTURES_DIR / "extraction_hard.json"
DEFAULT_CG_SEED = FIXTURES_DIR / "content_gate_seed.json"
DEFAULT_CG_HARD = FIXTURES_DIR / "content_gate_hard.json"
DEFAULT_DM_SEED = FIXTURES_DIR / "dedup_match_seed.json"
DEFAULT_DC_SEED = FIXTURES_DIR / "dedup_cluster_seed.json"
DEFAULT_EN_SEED = FIXTURES_DIR / "enrichment_seed.json"


def _load_classification_fixture(path: str):
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise SystemExit(f"Fixture not found: {fixture_path}")
    return load_fixture(json.loads(fixture_path.read_text())), str(fixture_path)


def _load_extraction_fixture_path(path: str):
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise SystemExit(f"Fixture not found: {fixture_path}")
    return load_extraction_fixture(json.loads(fixture_path.read_text())), str(fixture_path)


def _add_classification_commands(sub: argparse._SubParsersAction) -> None:
    cls = sub.add_parser("classification", help="Classification eval")
    cls_sub = cls.add_subparsers(dest="command", required=True)

    p_validate = cls_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_CLS_SEED))
    p_validate.set_defaults(stage="classification", handler="validate")

    p_build = cls_sub.add_parser("build", help="Sample pending cases from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=50)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(CLS_DEFAULT_OUT))
    p_build.add_argument("--merge-into", default=None)
    p_build.set_defaults(stage="classification", handler="build")

    p_generate = cls_sub.add_parser("generate-hard", help="Generate adversarial cases (costs tokens)")
    p_generate.add_argument("--out", default=str(DEFAULT_CLS_HARD))
    p_generate.add_argument("--model", default=None)
    p_generate.set_defaults(stage="classification", handler="generate-hard")

    p_run = cls_sub.add_parser("run", help="Run eval against labeled cases")
    p_run.add_argument("--fixture", default=str(DEFAULT_CLS_SEED))
    p_run.add_argument("--variant", default="baseline")
    p_run.add_argument("--concurrency", type=int, default=5)
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--ids", default=None)
    p_run.add_argument("--output", default=None)
    p_run.add_argument("--fail-fast", action="store_true")
    p_run.add_argument("--no-llm", action="store_true")
    p_run.set_defaults(stage="classification", handler="run")

    p_compare = cls_sub.add_parser("compare", help="Compare two run reports")
    p_compare.add_argument("--baseline", required=True)
    p_compare.add_argument("--candidate", required=True)
    p_compare.set_defaults(stage="classification", handler="compare")

    p_report = cls_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(stage="classification", handler="report")


def _add_extraction_commands(sub: argparse._SubParsersAction) -> None:
    ext = sub.add_parser("extraction", help="Extraction eval")
    ext_sub = ext.add_subparsers(dest="command", required=True)

    p_validate = ext_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_EXT_SEED))
    p_validate.set_defaults(stage="extraction", handler="validate")

    p_build = ext_sub.add_parser("build", help="Sample cases from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=30)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(EXT_DEFAULT_OUT))
    p_build.add_argument("--merge-into", default=None)
    p_build.add_argument(
        "--with-labels",
        action="store_true",
        help="Use existing extraction_data as expected (for seed bootstrap)",
    )
    p_build.set_defaults(stage="extraction", handler="build")

    p_generate = ext_sub.add_parser("generate-hard", help="Generate adversarial cases (costs tokens)")
    p_generate.add_argument("--out", default=str(DEFAULT_EXT_HARD))
    p_generate.add_argument("--model", default=None)
    p_generate.set_defaults(stage="extraction", handler="generate-hard")

    p_run = ext_sub.add_parser("run", help="Run eval against labeled cases")
    p_run.add_argument("--fixture", default=str(DEFAULT_EXT_SEED))
    p_run.add_argument("--variant", default="baseline")
    p_run.add_argument("--concurrency", type=int, default=3)
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--ids", default=None)
    p_run.add_argument("--output", default=None)
    p_run.add_argument("--fail-fast", action="store_true")
    p_run.add_argument("--no-llm", action="store_true")
    p_run.set_defaults(stage="extraction", handler="run")

    p_report = ext_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(stage="extraction", handler="report")


def _add_run_args(parser: argparse.ArgumentParser, *, default_fixture: str, concurrency: int) -> None:
    parser.add_argument("--fixture", default=default_fixture)
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--concurrency", type=int, default=concurrency)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ids", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--no-llm", action="store_true")


def _add_content_gate_commands(sub: argparse._SubParsersAction) -> None:
    cg = sub.add_parser("content-gate", help="Content gate (article body) eval")
    cg_sub = cg.add_subparsers(dest="command", required=True)

    p_validate = cg_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_CG_HARD))
    p_validate.set_defaults(stage="content-gate", handler="validate")

    p_build = cg_sub.add_parser("build", help="Sample gate-passing articles from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=15)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(DEFAULT_CG_SEED))
    p_build.add_argument("--merge-into", default=None)
    p_build.add_argument("--with-labels", action="store_true")
    p_build.set_defaults(stage="content-gate", handler="build")

    p_generate = cg_sub.add_parser("generate-hard", help="Generate adversarial articles (costs tokens)")
    p_generate.add_argument("--out", default=str(DEFAULT_CG_HARD))
    p_generate.add_argument("--model", default=None)
    p_generate.set_defaults(stage="content-gate", handler="generate-hard")

    p_run = cg_sub.add_parser("run", help="Run eval against labeled cases")
    _add_run_args(p_run, default_fixture=str(DEFAULT_CG_HARD), concurrency=4)
    p_run.set_defaults(stage="content-gate", handler="run")

    p_report = cg_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(stage="content-gate", handler="report")


def _add_dedup_match_commands(sub: argparse._SubParsersAction) -> None:
    dm = sub.add_parser("dedup-match", help="Dedup match (raw event vs candidates) eval")
    dm_sub = dm.add_subparsers(dest="command", required=True)

    p_validate = dm_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_DM_SEED))
    p_validate.set_defaults(stage="dedup-match", handler="validate")

    p_build = dm_sub.add_parser("build", help="Sample matched/unmatched cases from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=30)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(DEFAULT_DM_SEED))
    p_build.add_argument("--merge-into", default=None)
    p_build.set_defaults(stage="dedup-match", handler="build")

    p_run = dm_sub.add_parser("run", help="Run eval against labeled cases")
    _add_run_args(p_run, default_fixture=str(DEFAULT_DM_SEED), concurrency=4)
    p_run.set_defaults(stage="dedup-match", handler="run")

    p_report = dm_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(stage="dedup-match", handler="report")


def _add_dedup_cluster_commands(sub: argparse._SubParsersAction) -> None:
    dc = sub.add_parser("dedup-cluster", help="Dedup cluster (batch grouping) eval")
    dc_sub = dc.add_subparsers(dest="command", required=True)

    p_validate = dc_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_DC_SEED))
    p_validate.set_defaults(stage="dedup-cluster", handler="validate")

    p_build = dc_sub.add_parser("build", help="Sample cluster groups from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=25)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(DEFAULT_DC_SEED))
    p_build.add_argument("--merge-into", default=None)
    p_build.set_defaults(stage="dedup-cluster", handler="build")

    p_run = dc_sub.add_parser("run", help="Run eval against labeled cases")
    _add_run_args(p_run, default_fixture=str(DEFAULT_DC_SEED), concurrency=4)
    p_run.set_defaults(stage="dedup-cluster", handler="run")

    p_report = dc_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(stage="dedup-cluster", handler="report")


def _add_enrichment_commands(sub: argparse._SubParsersAction) -> None:
    en = sub.add_parser("enrichment", help="Enrichment synthesis eval")
    en_sub = en.add_subparsers(dest="command", required=True)

    p_validate = en_sub.add_parser("validate", help="Validate fixture schema")
    p_validate.add_argument("--fixture", default=str(DEFAULT_EN_SEED))
    p_validate.set_defaults(stage="enrichment", handler="validate")

    p_build = en_sub.add_parser("build", help="Sample enriched unique events from DB copy")
    p_build.add_argument("--db", required=True)
    p_build.add_argument("--n", type=int, default=25)
    p_build.add_argument("--seed", type=int, default=42)
    p_build.add_argument("--out", default=str(DEFAULT_EN_SEED))
    p_build.add_argument("--merge-into", default=None)
    p_build.add_argument("--with-labels", action="store_true")
    p_build.set_defaults(stage="enrichment", handler="build")

    p_run = en_sub.add_parser("run", help="Run eval against labeled cases")
    _add_run_args(p_run, default_fixture=str(DEFAULT_EN_SEED), concurrency=4)
    p_run.set_defaults(stage="enrichment", handler="run")

    p_report = en_sub.add_parser("report", help="Print a run report summary")
    p_report.add_argument("--run", required=True)
    p_report.set_defaults(stage="enrichment", handler="report")


def _add_improvement_commands(sub: argparse._SubParsersAction) -> None:
    imp = sub.add_parser("improvement", help="Prod anomaly detect / verify / propose / run-all")
    imp_sub = imp.add_subparsers(dest="command", required=True)

    p_detect = imp_sub.add_parser("detect", help="Scan prod/staging for pipeline anomalies")
    p_detect.add_argument("--only-stage", default="all", help="Stage name or 'all'")
    p_detect.add_argument("--limit", type=int, default=20, help="Max candidates per stage")
    p_detect.add_argument("--db", default=None, help="SQLite snapshot path (else DATABASE_URL)")
    p_detect.add_argument("--output", default=None, help="Write candidates JSON")
    p_detect.add_argument("--dry-run", action="store_true", help="Alias for detect without side effects")
    p_detect.set_defaults(stage="improvement", handler="detect")

    p_verify = imp_sub.add_parser("verify", help="Re-run production fns to confirm anomalies")
    p_verify.add_argument("--candidates", required=True)
    p_verify.add_argument("--output", default=None)
    p_verify.add_argument("--db", default=None)
    p_verify.add_argument("--concurrency", type=int, default=3)
    p_verify.add_argument(
        "--with-llm-extraction",
        action="store_true",
        help="Re-run extraction LLM (expensive)",
    )
    p_verify.set_defaults(stage="improvement", handler="verify")

    p_propose = imp_sub.add_parser("propose", help="Draft pending eval cases from verified anomalies")
    p_propose.add_argument("--verified", required=True)
    p_propose.add_argument("--output", default=None)
    p_propose.set_defaults(stage="improvement", handler="propose")

    p_run_all = imp_sub.add_parser("run-all", help="Run all stage evals and aggregate 100% gate")
    p_run_all.add_argument("--variant", default="baseline")
    p_run_all.add_argument("--concurrency", type=int, default=4)
    p_run_all.add_argument("--no-llm", action="store_true")
    p_run_all.add_argument("--output", default=None)
    p_run_all.set_defaults(stage="improvement", handler="run-all")

    p_compare = imp_sub.add_parser("compare-reports", help="Compare any two stage run reports")
    p_compare.add_argument("--baseline", required=True)
    p_compare.add_argument("--candidate", required=True)
    p_compare.set_defaults(stage="improvement", handler="compare-reports")


def dispatch(args: argparse.Namespace) -> None:
    handler = getattr(args, "handler", None)
    if args.stage == "improvement":
        _dispatch_improvement(args, handler)
        return

    if args.stage == "classification":
        if handler == "validate":
            fixture, fixture_path = _load_classification_fixture(args.fixture)
            result = validate_classification_fixture(fixture)
            print_classification_validation(result, fixture_path)
            if not result.valid:
                raise SystemExit(1)
        elif handler == "build":
            db_path = Path(args.db)
            if not db_path.exists():
                raise SystemExit(f"DB not found: {db_path}")
            merge_into = Path(args.merge_into) if args.merge_into else None
            fixture, added = build_classification_fixture(db_path, args.n, args.seed, merge_into)
            write_classification_fixture(fixture, Path(args.out))
            print(
                f"Wrote {args.out}: {added} new cases, "
                f"{fixture.meta.labeled_count} labeled, {fixture.meta.pending_count} pending"
            )
        elif handler == "generate-hard":
            from eval.stages.classification.generate_hard import (
                GENERATOR_MODEL,
                write_hard_fixture,
            )

            path, true_count, false_count = write_hard_fixture(
                Path(args.out), model=args.model or GENERATOR_MODEL
            )
            print(f"Wrote {path} (30 cases: {true_count} true, {false_count} false)")
            print(f"  generator: {args.model or GENERATOR_MODEL}")
        elif handler == "run":
            asyncio.run(_run_classification(args))
        elif handler == "compare":
            baseline = load_report(Path(args.baseline))
            candidate = load_report(Path(args.candidate))
            print_compare(compare_reports(baseline, candidate))
        elif handler == "report":
            from eval.stages.classification.run import print_report

            print_report(load_report(Path(args.run)))
        return

    if args.stage == "extraction":
        if handler == "validate":
            fixture, fixture_path = _load_extraction_fixture_path(args.fixture)
            result = validate_extraction_fixture(fixture)
            print_extraction_validation(result, fixture_path)
            if not result.valid:
                raise SystemExit(1)
        elif handler == "build":
            db_path = Path(args.db)
            if not db_path.exists():
                raise SystemExit(f"DB not found: {db_path}")
            merge_into = Path(args.merge_into) if args.merge_into else None
            fixture, added = build_extraction_fixture(
                db_path,
                args.n,
                args.seed,
                with_labels=args.with_labels,
                merge_into=merge_into,
            )
            write_extraction_fixture(fixture, Path(args.out))
            print(
                f"Wrote {args.out}: {added} new cases, "
                f"{fixture.meta.labeled_count} labeled, {fixture.meta.pending_count} pending"
            )
        elif handler == "generate-hard":
            from eval.stages.extraction.generate_hard import (
                GENERATOR_MODEL,
                write_hard_fixture,
            )

            path = write_hard_fixture(Path(args.out), model=args.model or GENERATOR_MODEL)
            print(f"Wrote {path}")
            print(f"  generator: {args.model or GENERATOR_MODEL}")
        elif handler == "run":
            asyncio.run(_run_extraction(args))
        elif handler == "report":
            from eval.schemas_extraction import ExtractionRunReport
            from eval.stages.extraction.run import print_report as print_ext_report

            print_ext_report(ExtractionRunReport.model_validate(json.loads(Path(args.run).read_text())))
        return

    if args.stage == "content-gate":
        _dispatch_content_gate(args, handler)
        return

    if args.stage == "dedup-match":
        _dispatch_dedup_match(args, handler)
        return

    if args.stage == "dedup-cluster":
        _dispatch_dedup_cluster(args, handler)
        return

    if args.stage == "enrichment":
        _dispatch_enrichment(args, handler)
        return

    raise SystemExit(f"Unknown stage/handler: {args.stage}/{handler}")


def _dispatch_improvement(args: argparse.Namespace, handler: str | None) -> None:
    from eval.improvement.detect import parse_stages, print_detect_summary, run_detect
    from eval.improvement.propose import print_propose_summary, run_propose
    from eval.improvement.run_all import print_run_all_summary, run_all_evals
    from eval.improvement.verify import print_verify_summary, run_verify

    if handler == "detect":
        db_path = Path(args.db) if args.db else None
        if db_path and not db_path.exists():
            raise SystemExit(f"DB not found: {db_path}")
        stages = parse_stages(args.only_stage)
        output = Path(args.output) if args.output else None
        bundle = asyncio.run(
            run_detect(
                db_path=db_path,
                stages=stages,
                limit=args.limit,
                output=output,
                dry_run=args.dry_run,
            )
        )
        print_detect_summary(bundle)
        if output:
            print(f"\nWrote {output}")
        return

    if handler == "verify":
        db_path = Path(args.db) if args.db else None
        output = Path(args.output) if args.output else None
        bundle = asyncio.run(
            run_verify(
                candidates_path=Path(args.candidates),
                output=output,
                db_path=db_path,
                with_llm_extraction=args.with_llm_extraction,
                concurrency=args.concurrency,
            )
        )
        print_verify_summary(bundle)
        if output:
            print(f"\nWrote {output}")
        return

    if handler == "propose":
        output = Path(args.output) if args.output else None
        bundle = asyncio.run(
            run_propose(verified_path=Path(args.verified), output=output)
        )
        print_propose_summary(bundle)
        if output:
            print(f"\nWrote {output}")
        return

    if handler == "run-all":
        output = Path(args.output) if args.output else None
        payload = asyncio.run(
            run_all_evals(
                variant=args.variant,
                concurrency=args.concurrency,
                dry_run=args.no_llm,
                output=output,
            )
        )
        print_run_all_summary(payload)
        if output:
            print(f"\nWrote {output}")
        if not payload["summary"]["all_passed"]:
            raise SystemExit(1)
        return

    if handler == "compare-reports":
        result = compare_generic_reports(Path(args.baseline), Path(args.candidate))
        print_compare(result)
        return

    raise SystemExit(f"Unknown improvement handler: {handler}")


def _require_db(args: argparse.Namespace) -> Path:
    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    return db_path


def _load_json_fixture(path: str, loader):
    fixture_path = Path(path)
    if not fixture_path.exists():
        raise SystemExit(f"Fixture not found: {fixture_path}")
    return loader(json.loads(fixture_path.read_text())), str(fixture_path)


def _print_build_result(out: str, added: int, fixture) -> None:
    print(
        f"Wrote {out}: {added} new cases, "
        f"{fixture.meta.labeled_count} labeled, {fixture.meta.pending_count} pending"
    )


def _dispatch_content_gate(args: argparse.Namespace, handler: str | None) -> None:
    from eval.schemas_content_gate import ContentGateRunReport, load_content_gate_fixture
    from eval.stages.content_gate.build import build_fixture, write_fixture
    from eval.stages.content_gate.validate import print_validation, validate_fixture

    if handler == "validate":
        fixture, fixture_path = _load_json_fixture(args.fixture, load_content_gate_fixture)
        result = validate_fixture(fixture)
        print_validation(result, fixture_path)
        if not result.valid:
            raise SystemExit(1)
    elif handler == "build":
        db_path = _require_db(args)
        merge_into = Path(args.merge_into) if args.merge_into else None
        fixture, added = build_fixture(
            db_path, args.n, args.seed, with_labels=args.with_labels, merge_into=merge_into
        )
        write_fixture(fixture, Path(args.out))
        _print_build_result(args.out, added, fixture)
    elif handler == "generate-hard":
        from eval.stages.content_gate.generate_hard import GENERATOR_MODEL, write_hard_fixture

        path, gate_true, gate_false = write_hard_fixture(
            Path(args.out), model=args.model or GENERATOR_MODEL
        )
        print(f"Wrote {path} ({gate_true} gate=true, {gate_false} gate=false)")
        print(f"  generator: {args.model or GENERATOR_MODEL}")
    elif handler == "run":
        asyncio.run(_run_generic(args, "content_gate"))
    elif handler == "report":
        from eval.stages.content_gate.run import print_report

        print_report(ContentGateRunReport.model_validate(json.loads(Path(args.run).read_text())))


def _dispatch_dedup_match(args: argparse.Namespace, handler: str | None) -> None:
    from eval.schemas_dedup import DedupMatchRunReport, load_dedup_match_fixture
    from eval.stages.dedup_match.build import build_fixture, write_fixture
    from eval.stages.dedup_match.validate import print_validation, validate_fixture

    if handler == "validate":
        fixture, fixture_path = _load_json_fixture(args.fixture, load_dedup_match_fixture)
        result = validate_fixture(fixture)
        print_validation(result, fixture_path)
        if not result.valid:
            raise SystemExit(1)
    elif handler == "build":
        db_path = _require_db(args)
        merge_into = Path(args.merge_into) if args.merge_into else None
        fixture, added = build_fixture(db_path, args.n, args.seed, merge_into=merge_into)
        write_fixture(fixture, Path(args.out))
        _print_build_result(args.out, added, fixture)
    elif handler == "run":
        asyncio.run(_run_generic(args, "dedup_match"))
    elif handler == "report":
        from eval.stages.dedup_match.run import print_report

        print_report(DedupMatchRunReport.model_validate(json.loads(Path(args.run).read_text())))


def _dispatch_dedup_cluster(args: argparse.Namespace, handler: str | None) -> None:
    from eval.schemas_dedup import DedupClusterRunReport, load_dedup_cluster_fixture
    from eval.stages.dedup_cluster.build import build_fixture, write_fixture
    from eval.stages.dedup_cluster.validate import print_validation, validate_fixture

    if handler == "validate":
        fixture, fixture_path = _load_json_fixture(args.fixture, load_dedup_cluster_fixture)
        result = validate_fixture(fixture)
        print_validation(result, fixture_path)
        if not result.valid:
            raise SystemExit(1)
    elif handler == "build":
        db_path = _require_db(args)
        merge_into = Path(args.merge_into) if args.merge_into else None
        fixture, added = build_fixture(db_path, args.n, args.seed, merge_into=merge_into)
        write_fixture(fixture, Path(args.out))
        _print_build_result(args.out, added, fixture)
    elif handler == "run":
        asyncio.run(_run_generic(args, "dedup_cluster"))
    elif handler == "report":
        from eval.stages.dedup_cluster.run import print_report

        print_report(DedupClusterRunReport.model_validate(json.loads(Path(args.run).read_text())))


def _dispatch_enrichment(args: argparse.Namespace, handler: str | None) -> None:
    from eval.schemas_enrichment import EnrichmentRunReport, load_enrichment_fixture
    from eval.stages.enrichment.build import build_fixture, write_fixture
    from eval.stages.enrichment.validate import print_validation, validate_fixture

    if handler == "validate":
        fixture, fixture_path = _load_json_fixture(args.fixture, load_enrichment_fixture)
        result = validate_fixture(fixture)
        print_validation(result, fixture_path)
        if not result.valid:
            raise SystemExit(1)
    elif handler == "build":
        db_path = _require_db(args)
        merge_into = Path(args.merge_into) if args.merge_into else None
        fixture, added = build_fixture(
            db_path, args.n, args.seed, with_labels=args.with_labels, merge_into=merge_into
        )
        write_fixture(fixture, Path(args.out))
        _print_build_result(args.out, added, fixture)
    elif handler == "run":
        asyncio.run(_run_generic(args, "enrichment"))
    elif handler == "report":
        from eval.stages.enrichment.run import print_report

        print_report(EnrichmentRunReport.model_validate(json.loads(Path(args.run).read_text())))


_GENERIC_RUNNERS = {
    "content_gate": (
        "eval.schemas_content_gate",
        "load_content_gate_fixture",
        "eval.stages.content_gate.run",
        "run_content_gate_eval",
    ),
    "dedup_match": (
        "eval.schemas_dedup",
        "load_dedup_match_fixture",
        "eval.stages.dedup_match.run",
        "run_dedup_match_eval",
    ),
    "dedup_cluster": (
        "eval.schemas_dedup",
        "load_dedup_cluster_fixture",
        "eval.stages.dedup_cluster.run",
        "run_dedup_cluster_eval",
    ),
    "enrichment": (
        "eval.schemas_enrichment",
        "load_enrichment_fixture",
        "eval.stages.enrichment.run",
        "run_enrichment_eval",
    ),
}


async def _run_generic(args: argparse.Namespace, stage_key: str) -> None:
    import importlib

    schemas_mod_name, loader_name, run_mod_name, runner_name = _GENERIC_RUNNERS[stage_key]
    schemas_mod = importlib.import_module(schemas_mod_name)
    run_mod = importlib.import_module(run_mod_name)

    loader = getattr(schemas_mod, loader_name)
    runner = getattr(run_mod, runner_name)

    fixture, fixture_path = _load_json_fixture(args.fixture, loader)
    case_ids = {s.strip() for s in args.ids.split(",") if s.strip()} if args.ids else None
    report = await runner(
        fixture,
        variant_name=args.variant,
        concurrency=args.concurrency,
        limit=args.limit,
        case_ids=case_ids,
        fail_fast=args.fail_fast,
        dry_run=args.no_llm,
        fixture_path=fixture_path,
    )
    run_mod.print_report(report)
    if args.output:
        output_path = Path(args.output)
    elif args.no_llm:
        output_path = None
    else:
        output_path = run_mod.default_output_path(args.variant)
    if output_path:
        run_mod.write_report(report, output_path)
        print(f"\nWrote {output_path}")


async def _run_classification(args: argparse.Namespace) -> None:
    from eval.stages.classification.run import (
        default_output_path,
        print_report,
        run_classification_eval,
        write_report,
    )

    fixture, fixture_path = _load_classification_fixture(args.fixture)
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


async def _run_extraction(args: argparse.Namespace) -> None:
    from eval.stages.extraction.run import (
        default_output_path,
        print_report,
        run_extraction_eval,
        write_report,
    )

    fixture, fixture_path = _load_extraction_fixture_path(args.fixture)
    case_ids = {s.strip() for s in args.ids.split(",") if s.strip()} if args.ids else None
    report = await run_extraction_eval(
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline eval harness")
    sub = parser.add_subparsers(dest="stage", required=True)
    _add_classification_commands(sub)
    _add_extraction_commands(sub)
    _add_content_gate_commands(sub)
    _add_dedup_match_commands(sub)
    _add_dedup_cluster_commands(sub)
    _add_enrichment_commands(sub)
    _add_improvement_commands(sub)
    args = parser.parse_args()
    dispatch(args)


if __name__ == "__main__":
    main()
