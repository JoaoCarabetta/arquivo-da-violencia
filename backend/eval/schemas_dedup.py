"""Pydantic schemas for dedup-match and dedup-cluster eval fixtures and reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eval.schemas import CaseMetadata, LabelStatus, ValidationIssue, ValidationResult, utc_now_iso

__all__ = ["utc_now_iso"]


class RawEventData(BaseModel):
    """Plain-dict projection of a RawEvent, enough for the dedup prompts."""

    id: int
    title: str | None = None
    event_date: str | None = None  # YYYY-MM-DD
    city: str | None = None
    state: str | None = None
    neighborhood: str | None = None
    homicide_type: str | None = None
    chronological_description: str | None = None
    victim_names: list[str] = Field(default_factory=list)


class UniqueEventData(BaseModel):
    """Plain-dict projection of a UniqueEvent, enough for the dedup match prompt."""

    id: int
    title: str | None = None
    event_date: str | None = None
    city: str | None = None
    state: str | None = None
    neighborhood: str | None = None
    homicide_type: str | None = None
    chronological_description: str | None = None
    victims_summary: str | None = None
    victim_count: int | None = None
    source_count: int = 1


# --- dedup match -----------------------------------------------------------


class DedupMatchInput(BaseModel):
    raw_event: RawEventData
    candidates: list[UniqueEventData]


class DedupMatchExpected(BaseModel):
    match: bool
    unique_event_id: int | None = None


class DedupMatchCase(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    label_status: LabelStatus
    input: DedupMatchInput
    expected: DedupMatchExpected | None = None
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)


class DedupMatchFixtureMeta(BaseModel):
    stage: Literal["dedup_match"] = "dedup_match"
    version: int = 1
    source_db: str | None = None
    seed: int | None = None
    labeled_count: int = 0
    pending_count: int = 0
    generator_model: str | None = None


class DedupMatchFixture(BaseModel):
    meta: DedupMatchFixtureMeta
    cases: list[DedupMatchCase]


class DedupMatchCaseResult(BaseModel):
    id: str
    passed: bool
    expected_match: bool | None = None
    actual_match: bool | None = None
    expected_id: int | None = None
    actual_id: int | None = None
    confidence: float | None = None
    reasoning: str | None = None
    tags: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    error: str | None = None


class DedupMatchRunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    by_tag: dict[str, dict[str, Any]] = Field(default_factory=dict)


class DedupMatchRunMeta(BaseModel):
    stage: Literal["dedup_match"] = "dedup_match"
    variant: str
    model: str
    fixture: str
    run_at: str
    dry_run: bool = False


class DedupMatchRunReport(BaseModel):
    meta: DedupMatchRunMeta
    summary: DedupMatchRunSummary
    cases: list[DedupMatchCaseResult]


# --- dedup cluster ---------------------------------------------------------


class DedupClusterInput(BaseModel):
    events: list[RawEventData]


class DedupClusterExpected(BaseModel):
    # 1-based indices into input.events; every event appears in exactly one cluster
    clusters: list[list[int]]


class DedupClusterCase(BaseModel):
    id: str
    tags: list[str] = Field(default_factory=list)
    label_status: LabelStatus
    input: DedupClusterInput
    expected: DedupClusterExpected | None = None
    metadata: CaseMetadata = Field(default_factory=CaseMetadata)


class DedupClusterFixtureMeta(BaseModel):
    stage: Literal["dedup_cluster"] = "dedup_cluster"
    version: int = 1
    source_db: str | None = None
    seed: int | None = None
    labeled_count: int = 0
    pending_count: int = 0
    generator_model: str | None = None


class DedupClusterFixture(BaseModel):
    meta: DedupClusterFixtureMeta
    cases: list[DedupClusterCase]


class DedupClusterCaseResult(BaseModel):
    id: str
    passed: bool  # exact partition match
    pairwise_precision: float | None = None
    pairwise_recall: float | None = None
    pairwise_f1: float | None = None
    expected_clusters: list[list[int]] = Field(default_factory=list)
    actual_clusters: list[list[int]] = Field(default_factory=list)
    reasoning: str | None = None
    tags: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    error: str | None = None


class DedupClusterRunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    exact_match_rate: float | None = None
    mean_pairwise_f1: float | None = None
    by_tag: dict[str, dict[str, Any]] = Field(default_factory=dict)


class DedupClusterRunMeta(BaseModel):
    stage: Literal["dedup_cluster"] = "dedup_cluster"
    variant: str
    model: str
    fixture: str
    run_at: str
    dry_run: bool = False


class DedupClusterRunReport(BaseModel):
    meta: DedupClusterRunMeta
    summary: DedupClusterRunSummary
    cases: list[DedupClusterCaseResult]


# --- helpers ---------------------------------------------------------------


def load_dedup_match_fixture(data: dict[str, Any]) -> DedupMatchFixture:
    return DedupMatchFixture.model_validate(data)


def load_dedup_cluster_fixture(data: dict[str, Any]) -> DedupClusterFixture:
    return DedupClusterFixture.model_validate(data)


def update_dedup_fixture_counts(fixture):
    fixture.meta.labeled_count = sum(1 for c in fixture.cases if c.label_status == "labeled")
    fixture.meta.pending_count = sum(1 for c in fixture.cases if c.label_status == "pending")
    return fixture


def validate_dedup_match_fixture(fixture: DedupMatchFixture) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for case in fixture.cases:
        if case.id in seen_ids:
            issues.append(ValidationIssue(case_id=case.id, message="duplicate case id"))
        seen_ids.add(case.id)

        if not case.input.candidates:
            issues.append(ValidationIssue(case_id=case.id, message="no candidates"))

        if case.label_status == "labeled":
            if case.expected is None:
                issues.append(ValidationIssue(case_id=case.id, message="labeled case missing expected"))
            elif case.expected.match:
                candidate_ids = {c.id for c in case.input.candidates}
                if case.expected.unique_event_id not in candidate_ids:
                    issues.append(
                        ValidationIssue(
                            case_id=case.id,
                            message="expected unique_event_id not among candidates",
                        )
                    )

    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")
    blocking = [
        i
        for i in issues
        if "duplicate" in i.message or "no candidates" in i.message or "not among" in i.message
    ]
    return ValidationResult(
        valid=len(blocking) == 0,
        labeled_count=labeled,
        pending_count=pending,
        issues=issues,
    )


def validate_dedup_cluster_fixture(fixture: DedupClusterFixture) -> ValidationResult:
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for case in fixture.cases:
        if case.id in seen_ids:
            issues.append(ValidationIssue(case_id=case.id, message="duplicate case id"))
        seen_ids.add(case.id)

        n = len(case.input.events)
        if n < 2:
            issues.append(ValidationIssue(case_id=case.id, message="needs at least 2 events"))

        if case.label_status == "labeled":
            if case.expected is None:
                issues.append(ValidationIssue(case_id=case.id, message="labeled case missing expected"))
            else:
                flat = sorted(i for cluster in case.expected.clusters for i in cluster)
                if flat != list(range(1, n + 1)):
                    issues.append(
                        ValidationIssue(
                            case_id=case.id,
                            message="expected clusters must partition 1..n exactly once",
                        )
                    )

    labeled = sum(1 for c in fixture.cases if c.label_status == "labeled")
    pending = sum(1 for c in fixture.cases if c.label_status == "pending")
    blocking = [
        i
        for i in issues
        if "duplicate" in i.message or "partition" in i.message or "at least 2" in i.message
    ]
    return ValidationResult(
        valid=len(blocking) == 0,
        labeled_count=labeled,
        pending_count=pending,
        issues=issues,
    )
