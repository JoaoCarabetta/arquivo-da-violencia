"""Pydantic schemas for enrichment-synthesis eval fixtures and reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.schemas import CaseMetadata, LabelStatus, ValidationIssue, ValidationResult, utc_now_iso

__all__ = ["utc_now_iso"]

DEFAULT_ENRICHMENT_REQUIRED_FIELDS = [
    "event_date",
    "city",
    "state",
    "victim_count",
]


class EnrichmentSource(BaseModel):
    publisher: str | None = None
    headline: str | None = None
    url: str | None = None
    content: str = ""
    extraction: dict[str, Any] | None = None
    victim_count: int | None = None
    city: str | None = None


class EnrichmentInput(BaseModel):
    current_state: dict[str, Any] = Field(default_factory=dict)
    sources: list[EnrichmentSource]


class EnrichmentScoring(BaseModel):
    required_fields: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ENRICHMENT_REQUIRED_FIELDS)
    )


class EnrichmentCase(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    label_status: LabelStatus
    input: EnrichmentInput
    expected: dict[str, Any] | None = None
    scoring: EnrichmentScoring = Field(default_factory=EnrichmentScoring)
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)


class EnrichmentFixtureMeta(BaseModel):
    stage: Literal["enrichment"] = "enrichment"
    version: int = 1
    source_db: str | None = None
    seed: int | None = None
    labeled_count: int = 0
    pending_count: int = 0
    generator_model: str | None = None


class EnrichmentFixture(BaseModel):
    meta: EnrichmentFixtureMeta
    cases: list[EnrichmentCase]


class EnrichmentCaseResult(BaseModel):
    id: str
    passed: bool
    score: float
    field_results: dict[str, bool] = Field(default_factory=dict)
    diff: dict[str, dict[str, Any]] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    error: str | None = None


class EnrichmentRunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    mean_score: float | None = None
    by_tag: dict[str, dict[str, Any]] = Field(default_factory=dict)
    by_field: dict[str, dict[str, Any]] = Field(default_factory=dict)


class EnrichmentRunMeta(BaseModel):
    stage: Literal["enrichment"] = "enrichment"
    variant: str
    model: str
    fixture: str
    run_at: str
    dry_run: bool = False


class EnrichmentRunReport(BaseModel):
    meta: EnrichmentRunMeta
    summary: EnrichmentRunSummary
    cases: list[EnrichmentCaseResult]


def load_enrichment_fixture(data: dict[str, Any]) -> EnrichmentFixture:
    return EnrichmentFixture.model_validate(data)


def dump_enrichment_fixture(fixture: EnrichmentFixture) -> dict[str, Any]:
    return fixture.model_dump(mode="json", exclude_none=False)


def update_enrichment_fixture_counts(fixture: EnrichmentFixture) -> EnrichmentFixture:
    fixture.meta.labeled_count = sum(1 for c in fixture.cases if c.label_status == "labeled")
    fixture.meta.pending_count = sum(1 for c in fixture.cases if c.label_status == "pending")
    return fixture


def validate_enrichment_fixture(fixture: EnrichmentFixture) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for case in fixture.cases:
        if case.id in seen_ids:
            issues.append(ValidationIssue(case_id=case.id, message="duplicate case id"))
        seen_ids.add(case.id)

        if not case.input.sources:
            issues.append(ValidationIssue(case_id=case.id, message="no sources"))

        if case.label_status == "labeled" and case.expected is None:
            issues.append(ValidationIssue(case_id=case.id, message="labeled case missing expected"))
        elif case.label_status == "pending" and case.expected is not None:
            issues.append(
                ValidationIssue(case_id=case.id, message="pending case should have expected=null")
            )

    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")
    blocking = [i for i in issues if "duplicate" in i.message or "no sources" in i.message]
    return ValidationResult(
        valid=len(blocking) == 0,
        labeled_count=labeled,
        pending_count=pending,
        issues=issues,
    )
