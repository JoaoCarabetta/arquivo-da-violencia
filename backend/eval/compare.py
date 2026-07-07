"""Compare eval run reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.schemas import RunReport


def load_report(path: Path) -> RunReport:
    data = json.loads(path.read_text())
    return RunReport.model_validate(data)


def load_generic_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def compare_case_results(
    baseline_cases: list[dict[str, Any]],
    candidate_cases: list[dict[str, Any]],
    *,
    baseline_variant: str = "baseline",
    candidate_variant: str = "candidate",
) -> dict[str, Any]:
    """Generic per-case pass/fail diff for any stage run report."""
    baseline_by_id = {c["id"]: c for c in baseline_cases if "id" in c}
    candidate_by_id = {c["id"]: c for c in candidate_cases if "id" in c}
    common_ids = sorted(set(baseline_by_id) & set(candidate_by_id))

    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    unchanged_pass = 0
    unchanged_fail = 0

    for case_id in common_ids:
        b = baseline_by_id[case_id]
        c = candidate_by_id[case_id]
        b_pass = bool(b.get("passed"))
        c_pass = bool(c.get("passed"))
        entry = {
            "id": case_id,
            "expected": c.get("expected", b.get("expected")),
            "baseline_actual": _pick_actual(b),
            "candidate_actual": _pick_actual(c),
        }
        if b_pass and not c_pass:
            regressions.append(entry)
        elif not b_pass and c_pass:
            improvements.append(entry)
        elif b_pass and c_pass:
            unchanged_pass += 1
        else:
            unchanged_fail += 1

    b_passed = sum(1 for c in baseline_cases if c.get("passed"))
    c_passed = sum(1 for c in candidate_cases if c.get("passed"))

    return {
        "baseline": {
            "variant": baseline_variant,
            "passed": b_passed,
            "total": len(baseline_cases),
        },
        "candidate": {
            "variant": candidate_variant,
            "passed": c_passed,
            "total": len(candidate_cases),
        },
        "common_cases": len(common_ids),
        "regressions": regressions,
        "improvements": improvements,
        "unchanged_pass": unchanged_pass,
        "unchanged_fail": unchanged_fail,
    }


def compare_generic_reports(baseline_path: Path, candidate_path: Path) -> dict[str, Any]:
    baseline = load_generic_report(baseline_path)
    candidate = load_generic_report(candidate_path)
    result = compare_case_results(
        baseline.get("cases", []),
        candidate.get("cases", []),
        baseline_variant=baseline.get("meta", {}).get("variant", "baseline"),
        candidate_variant=candidate.get("meta", {}).get("variant", "candidate"),
    )
    b_total = result["baseline"]["total"]
    c_total = result["candidate"]["total"]
    result["baseline"]["accuracy"] = (result["baseline"]["passed"] / b_total) if b_total else None
    result["candidate"]["accuracy"] = (result["candidate"]["passed"] / c_total) if c_total else None
    return result


def _pick_actual(case: dict[str, Any]) -> Any:
    for key in ("actual", "actual_match", "actual_gate", "actual_clusters"):
        if key in case:
            return case[key]
    if "field_results" in case:
        return case["field_results"]
    return None


def compare_reports(baseline: RunReport, candidate: RunReport) -> dict:
    baseline_by_id = {c.id: c for c in baseline.cases}
    candidate_by_id = {c.id: c for c in candidate.cases}

    common_ids = sorted(set(baseline_by_id) & set(candidate_by_id))
    regressions: list[dict] = []
    improvements: list[dict] = []
    unchanged_pass = 0
    unchanged_fail = 0

    for case_id in common_ids:
        b = baseline_by_id[case_id]
        c = candidate_by_id[case_id]
        if b.passed and not c.passed:
            regressions.append(
                {
                    "id": case_id,
                    "headline": c.headline or b.headline,
                    "expected": c.expected,
                    "baseline_actual": b.actual,
                    "candidate_actual": c.actual,
                }
            )
        elif not b.passed and c.passed:
            improvements.append(
                {
                    "id": case_id,
                    "headline": c.headline or b.headline,
                    "expected": c.expected,
                    "baseline_actual": b.actual,
                    "candidate_actual": c.actual,
                }
            )
        elif b.passed and c.passed:
            unchanged_pass += 1
        else:
            unchanged_fail += 1

    return {
        "baseline": {
            "variant": baseline.meta.variant,
            "accuracy": baseline.summary.accuracy,
            "passed": baseline.summary.passed,
            "total": baseline.summary.total,
        },
        "candidate": {
            "variant": candidate.meta.variant,
            "accuracy": candidate.summary.accuracy,
            "passed": candidate.summary.passed,
            "total": candidate.summary.total,
        },
        "common_cases": len(common_ids),
        "regressions": regressions,
        "improvements": improvements,
        "unchanged_pass": unchanged_pass,
        "unchanged_fail": unchanged_fail,
    }


def print_compare(result: dict) -> None:
    b = result["baseline"]
    c = result["candidate"]
    print(f"\n=== COMPARE: {b['variant']} vs {c['variant']} ===")
    print(f"  baseline:  {b['passed']}/{b['total']} ({_pct(b.get('accuracy'))})")
    print(f"  candidate: {c['passed']}/{c['total']} ({_pct(c.get('accuracy'))})")
    print(f"  common cases: {result['common_cases']}")
    print(f"  unchanged pass: {result['unchanged_pass']}, unchanged fail: {result['unchanged_fail']}")

    if result["regressions"]:
        print(f"\n  REGRESSIONS ({len(result['regressions'])}):")
        for item in result["regressions"]:
            print(f"    - {item['id']}: expected={item['expected']}, was {item['baseline_actual']}, now {item['candidate_actual']}")
            if item.get("headline"):
                print(f"      \"{item['headline'][:80]}\"")

    if result["improvements"]:
        print(f"\n  IMPROVEMENTS ({len(result['improvements'])}):")
        for item in result["improvements"]:
            print(f"    + {item['id']}: expected={item['expected']}, was {item['baseline_actual']}, now {item['candidate_actual']}")
            if item.get("headline"):
                print(f"      \"{item['headline'][:80]}\"")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"
