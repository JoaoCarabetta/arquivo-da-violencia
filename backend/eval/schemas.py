"""Pydantic schemas for eval fixtures and run reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


LabelStatus = Literal["labeled", "pending"]


class ClassificationInput(BaseModel):
    headline: str


class ClassificationExpected(BaseModel):
    is_violent_death: bool


class CaseMetadata(BaseModel):
    source_id: int | None = None
    notes: str = ""


class ClassificationCase(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    label_status: LabelStatus
    input: ClassificationInput
    expected: ClassificationExpected | None = None
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)


class FixtureMeta(BaseModel):
    stage: Literal["classification"] = "classification"
    version: int = 1
    source_db: str | None = None
    seed: int | None = None
    labeled_count: int = 0
    pending_count: int = 0
    generator_model: str | None = None


class ClassificationFixture(BaseModel):
    meta: FixtureMeta
    cases: list[ClassificationCase]


class ValidationIssue(BaseModel):
    case_id: str | None
    message: str


class ValidationResult(BaseModel):
    valid: bool
    labeled_count: int
    pending_count: int
    issues: list[ValidationIssue] = Field(default_factory=list)


class CaseResult(BaseModel):
    id: str
    passed: bool
    expected: bool | None = None
    actual: bool | None = None
    confidence: str | None = None
    reasoning: str | None = None
    headline: str | None = None
    tags: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    error: str | None = None


class RunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    by_tag: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RunMeta(BaseModel):
    stage: Literal["classification"] = "classification"
    variant: str
    model: str
    fixture: str
    run_at: str
    dry_run: bool = False


class RunReport(BaseModel):
    meta: RunMeta
    summary: RunSummary
    cases: list[CaseResult]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_fixture(data: dict[str, Any]) -> ClassificationFixture:
    return ClassificationFixture.model_validate(data)


def dump_fixture(fixture: ClassificationFixture) -> dict[str, Any]:
    return fixture.model_dump(mode="json", exclude_none=False)


def update_fixture_counts(fixture: ClassificationFixture) -> ClassificationFixture:
    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")
    fixture.meta.labeled_count = labeled
    fixture.meta.pending_count = pending
    return fixture
