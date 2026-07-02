"""Validate classification fixture files."""

from __future__ import annotations

from eval.schemas import ClassificationCase, ClassificationFixture, ValidationIssue, ValidationResult


def validate_fixture(fixture: ClassificationFixture) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for case in fixture.cases:
        if case.id in seen_ids:
            issues.append(ValidationIssue(case_id=case.id, message="duplicate case id"))
        seen_ids.add(case.id)

        if not case.input.headline.strip():
            issues.append(ValidationIssue(case_id=case.id, message="empty headline"))

        if case.label_status == "labeled":
            if case.expected is None:
                issues.append(
                    ValidationIssue(
                        case_id=case.id,
                        message="labeled case missing expected.is_violent_death",
                    )
                )
        elif case.label_status == "pending":
            if case.expected is not None:
                issues.append(
                    ValidationIssue(
                        case_id=case.id,
                        message="pending case should have expected=null",
                    )
                )

    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")

    blocking = [i for i in issues if "duplicate" in i.message or "empty headline" in i.message]
    return ValidationResult(
        valid=len(blocking) == 0,
        labeled_count=labeled,
        pending_count=pending,
        issues=issues,
    )


def labeled_cases(fixture: ClassificationFixture) -> list[ClassificationCase]:
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
