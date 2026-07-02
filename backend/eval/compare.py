"""Compare two classification eval run reports."""

from __future__ import annotations

import json
from pathlib import Path

from eval.schemas import RunReport


def load_report(path: Path) -> RunReport:
    data = json.loads(path.read_text())
    return RunReport.model_validate(data)


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
    print(f"  baseline:  {b['passed']}/{b['total']} ({_pct(b['accuracy'])})")
    print(f"  candidate: {c['passed']}/{c['total']} ({_pct(c['accuracy'])})")
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
