"""Shared schemas for the eval improvement loop."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

StageName = Literal[
    "classification",
    "content-gate",
    "extraction",
    "dedup-match",
    "dedup-cluster",
    "enrichment",
]

ALL_STAGES: list[StageName] = [
    "classification",
    "content-gate",
    "extraction",
    "dedup-match",
    "dedup-cluster",
    "enrichment",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AnomalyCandidate(BaseModel):
    """A suspected pipeline mistake found in production data."""

    stage: StageName
    candidate_id: str
    signal: str
    reason: str
    prod_snapshot: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    record_ids: dict[str, int | str | list[int] | None] = Field(default_factory=dict)


class CandidateBundle(BaseModel):
    """Output of detect."""

    meta: dict[str, Any] = Field(default_factory=dict)
    candidates: list[AnomalyCandidate] = Field(default_factory=list)


class VerificationResult(BaseModel):
    """Output of verify for one candidate."""

    candidate_id: str
    stage: StageName
    verified: bool
    prod_outcome: dict[str, Any] = Field(default_factory=dict)
    rerun_outcome: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    candidate: AnomalyCandidate


class VerifiedBundle(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    results: list[VerificationResult] = Field(default_factory=list)


class ProposedCase(BaseModel):
    """Draft eval fixture case awaiting human label approval."""

    stage: StageName
    case: dict[str, Any]
    verification: VerificationResult
    suggested_expected: dict[str, Any] | None = None


class ProposedBundle(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    cases: list[ProposedCase] = Field(default_factory=list)


ChangeType = Literal["code", "prompt", "config", "ops", "eval"]
FixPriority = Literal["high", "medium", "low"]


class AffectedGroup(BaseModel):
    """One incident or location impacted by a fix."""

    label: str
    city: str | None = None
    event_date: str | None = None
    unique_event_ids: list[int] = Field(default_factory=list)
    raw_event_ids: list[int] = Field(default_factory=list)
    suggested_survivor_id: int | None = None
    pair_count: int = 0
    candidate_ids: list[str] = Field(default_factory=list)


class RootCauseHypothesis(BaseModel):
    hypothesis_id: str
    description: str
    likelihood: float = Field(ge=0.0, le=1.0)
    evidence_for: str
    how_to_confirm: str


class SolutionOption(BaseModel):
    option_id: str
    name: str
    description: str
    change_type: ChangeType
    change_targets: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    weighted_score: float = 0.0
    pros: str = ""
    cons: str = ""
    requires_eval: bool = False
    eval_rationale: str = ""
    eval_fixture: str | None = None


EvalPriority = Literal["required", "recommended", "optional", "not_needed"]


class EvalRecommendation(BaseModel):
    add_to_eval: bool
    priority: EvalPriority = "optional"
    rationale: str = ""
    suggested_cases: list[str] = Field(default_factory=list)
    fixture_path: str | None = None
    elected_requires_eval: bool = False


class FixCluster(BaseModel):
    """One problem/solution pair grouping all related pipeline errors."""

    fix_id: str
    stage: StageName
    signal: str
    sub_signal: str = ""
    title: str
    problem: str
    solution: str
    root_cause: str
    mechanism: str
    recommended_change: str
    change_targets: list[str] = Field(default_factory=list)
    change_type: ChangeType
    priority: FixPriority = "medium"
    candidate_ids: list[str] = Field(default_factory=list)
    example_ids: list[str] = Field(default_factory=list)
    affected: list[AffectedGroup] = Field(default_factory=list)
    evidence: str = ""
    verified_count: int = 0
    total_count: int = 0
    context: dict[str, Any] = Field(default_factory=dict)
    root_causes: list[RootCauseHypothesis] = Field(default_factory=list)
    solutions: list[SolutionOption] = Field(default_factory=list)
    elected_solution_id: str = ""
    eval_recommendation: EvalRecommendation | None = None


class DiagnosisReport(BaseModel):
    meta: dict[str, Any] = Field(default_factory=dict)
    clusters: list[FixCluster] = Field(default_factory=list)
