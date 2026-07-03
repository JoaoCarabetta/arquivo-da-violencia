"""Pydantic schemas for extraction eval fixtures and run reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.schemas import CaseMetadata, LabelStatus, ValidationIssue, ValidationResult

DEFAULT_REQUIRED_FIELDS = [
    "date_time.date",
    "location_info.city",
    "location_info.state",
    "victims.number_of_victims",
    "homicide_dynamic.homicide_type",
    "homicide_dynamic.method",
]


class ExtractionMetadata(BaseModel):
    headline: str | None = None
    published_at: str | None = None
    publisher: str | None = None
    url: str | None = None


class ExtractionInput(BaseModel):
    content: str
    metadata: ExtractionMetadata = Field(default_factory=ExtractionMetadata)


class CaseScoring(BaseModel):
    required_fields: list[str] = Field(default_factory=lambda: list(DEFAULT_REQUIRED_FIELDS))


class ExtractionCase(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    label_status: LabelStatus
    input: ExtractionInput
    expected: dict[str, Any] | None = None
    scoring: CaseScoring = Field(default_factory=CaseScoring)
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)


class ExtractionFixtureMeta(BaseModel):
    stage: Literal["extraction"] = "extraction"
    version: int = 1
    source_db: str | None = None
    seed: int | None = None
    labeled_count: int = 0
    pending_count: int = 0
    generator_model: str | None = None


class ExtractionFixture(BaseModel):
    meta: ExtractionFixtureMeta
    cases: list[ExtractionCase]


class ExtractionCaseResult(BaseModel):
    id: str
    passed: bool
    score: float
    field_results: dict[str, bool] = Field(default_factory=dict)
    diff: dict[str, dict[str, Any]] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    headline: str | None = None
    latency_ms: int | None = None
    error: str | None = None


class ExtractionRunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    mean_score: float | None = None
    by_tag: dict[str, dict[str, Any]] = Field(default_factory=dict)
    by_field: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ExtractionRunMeta(BaseModel):
    stage: Literal["extraction"] = "extraction"
    variant: str
    model: str
    fixture: str
    run_at: str
    dry_run: bool = False


class ExtractionRunReport(BaseModel):
    meta: ExtractionRunMeta
    summary: ExtractionRunSummary
    cases: list[ExtractionCaseResult]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_extraction_fixture(data: dict[str, Any]) -> ExtractionFixture:
    return ExtractionFixture.model_validate(data)


def dump_extraction_fixture(fixture: ExtractionFixture) -> dict[str, Any]:
    return fixture.model_dump(mode="json", exclude_none=False)


def update_extraction_fixture_counts(fixture: ExtractionFixture) -> ExtractionFixture:
    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")
    fixture.meta.labeled_count = labeled
    fixture.meta.pending_count = pending
    return fixture


def validate_extraction_fixture(fixture: ExtractionFixture) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for case in fixture.cases:
        if case.id in seen_ids:
            issues.append(ValidationIssue(case_id=case.id, message="duplicate case id"))
        seen_ids.add(case.id)

        if not case.input.content.strip():
            issues.append(ValidationIssue(case_id=case.id, message="empty content"))

        if case.label_status == "labeled":
            if case.expected is None:
                issues.append(
                    ValidationIssue(case_id=case.id, message="labeled case missing expected")
                )
        elif case.label_status == "pending" and case.expected is not None:
            issues.append(
                ValidationIssue(
                    case_id=case.id,
                    message="pending case should have expected=null",
                )
            )

    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")
    blocking = [i for i in issues if "duplicate" in i.message or "empty content" in i.message]
    return ValidationResult(
        valid=len(blocking) == 0,
        labeled_count=labeled,
        pending_count=pending,
        issues=issues,
    )
