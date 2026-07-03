"""Validate extraction fixture files."""

from __future__ import annotations

from eval.schemas import ValidationResult
from eval.schemas_extraction import ExtractionFixture, validate_extraction_fixture


def validate_fixture(fixture: ExtractionFixture) -> ValidationResult:
    return validate_extraction_fixture(fixture)


def labeled_cases(fixture: ExtractionFixture):
    return [
        c
        for c in fixture.cases
        if c.label_status == "labeled" and c.expected is not None
    ]


def print_validation(result: ValidationResult, fixture_path: str) -> None:
    print(f"\n=== VALIDATE: {fixture_path} ===")
    print(f"  labeled: {result.labeled_count}, pending: {result.pending_count}")
    if result.valid:
        print("  schema: OK")
    else:
        print("  schema: INVALID")

    if result.issues:
        print(f"  issues ({len(result.issues)}):")
        for issue in result.issues:
            prefix = issue.case_id or "fixture"
            print(f"    - [{prefix}] {issue.message}")
