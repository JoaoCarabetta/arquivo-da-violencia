"""Validate dedup-match fixture files."""

from __future__ import annotations

from eval.schemas import ValidationResult
from eval.schemas_dedup import DedupMatchFixture, validate_dedup_match_fixture


def validate_fixture(fixture: DedupMatchFixture) -> ValidationResult:
    return validate_dedup_match_fixture(fixture)


def labeled_cases(fixture: DedupMatchFixture):
    return [
        c
        for c in fixture.cases
        if c.label_status == "labeled" and c.expected is not None
    ]


def print_validation(result: ValidationResult, fixture_path: str) -> None:
    print(f"\n=== VALIDATE: {fixture_path} ===")
    print(f"  labeled: {result.labeled_count}, pending: {result.pending_count}")
    print("  schema: OK" if result.valid else "  schema: INVALID")

    if result.issues:
        print(f"  issues ({len(result.issues)}):")
        for issue in result.issues:
            print(f"    - [{issue.case_id or 'fixture'}] {issue.message}")
