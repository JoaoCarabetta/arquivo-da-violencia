"""Pydantic schemas for content-gate eval fixtures and run reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.schemas import CaseMetadata, LabelStatus, ValidationIssue, ValidationResult, utc_now_iso

__all__ = ["utc_now_iso"]


class ContentGateInput(BaseModel):
    headline: str
    content: str


class ContentGateExpected(BaseModel):
    is_violent_death: bool
    is_single_incident: bool

    @property
    def passes_gate(self) -> bool:
        return self.is_violent_death and self.is_single_incident


class ContentGateCase(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    label_status: LabelStatus
    input: ContentGateInput
    expected: ContentGateExpected | None = None
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)


class ContentGateFixtureMeta(BaseModel):
    stage: Literal["content_gate"] = "content_gate"
    version: int = 1
    source_db: str | None = None
    seed: int | None = None
    labeled_count: int = 0
    pending_count: int = 0
    generator_model: str | None = None


class ContentGateFixture(BaseModel):
    meta: ContentGateFixtureMeta
    cases: list[ContentGateCase]


class ContentGateCaseResult(BaseModel):
    id: str
    passed: bool
    expected_gate: bool | None = None
    actual_gate: bool | None = None
    actual_is_violent_death: bool | None = None
    actual_is_single_incident: bool | None = None
    confidence: str | None = None
    reasoning: str | None = None
    headline: str | None = None
    tags: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    error: str | None = None


class ContentGateRunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    by_tag: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ContentGateRunMeta(BaseModel):
    stage: Literal["content_gate"] = "content_gate"
    variant: str
    model: str
    fixture: str
    run_at: str
    dry_run: bool = False


class ContentGateRunReport(BaseModel):
    meta: ContentGateRunMeta
    summary: ContentGateRunSummary
    cases: list[ContentGateCaseResult]


def load_content_gate_fixture(data: dict[str, Any]) -> ContentGateFixture:
    return ContentGateFixture.model_validate(data)


def dump_content_gate_fixture(fixture: ContentGateFixture) -> dict[str, Any]:
    return fixture.model_dump(mode="json", exclude_none=False)


def update_content_gate_fixture_counts(fixture: ContentGateFixture) -> ContentGateFixture:
    fixture.meta.labeled_count = sum(1 for c in fixture.cases if c.label_status == "labeled")
    fixture.meta.pending_count = sum(1 for c in fixture.cases if c.label_status == "pending")
    return fixture


def validate_content_gate_fixture(fixture: ContentGateFixture) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for case in fixture.cases:
        if case.id in seen_ids:
            issues.append(ValidationIssue(case_id=case.id, message="duplicate case id"))
        seen_ids.add(case.id)

        if not case.input.content.strip():
            issues.append(ValidationIssue(case_id=case.id, message="empty content"))

        if case.label_status == "labeled" and case.expected is None:
            issues.append(ValidationIssue(case_id=case.id, message="labeled case missing expected"))
        elif case.label_status == "pending" and case.expected is not None:
            issues.append(
                ValidationIssue(case_id=case.id, message="pending case should have expected=null")
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
