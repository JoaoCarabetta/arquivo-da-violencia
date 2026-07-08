"""Cluster pipeline errors, diagnose root causes, and recommend algorithm changes."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from eval.improvement.analysis import analyze_report_clusters
from eval.improvement.schemas import (
    AffectedGroup,
    AnomalyCandidate,
    ChangeType,
    DiagnosisReport,
    FixCluster,
    FixPriority,
    VerificationResult,
)

# Maps (stage, signal, sub_signal) → diagnosis template.
# sub_signal is optional (use "" when not applicable).
DiagnosisTemplate = dict[str, Any]

DIAGNOSIS: dict[tuple[str, str, str], DiagnosisTemplate] = {
    (
        "dedup-match",
        "near_duplicate_unique_events",
        "victim_name",
    ): {
        "problem_title": "Duplicate UniqueEvents not merged after ingest",
        "solution_summary": "Run near-dup merge and schedule post-dedup maintenance scan",
        "root_cause": "Same victim identified on multiple UniqueEvents for one incident",
        "mechanism": (
            "Sources created separate UniqueEvents during batch clustering or ingest. "
            "Heuristic `pair_signal` detects victim overlap but no merge ran."
        ),
        "recommended_change": (
            "1) Run `merge_near_duplicate_unique_events` on prod/staging to heal existing dupes. "
            "2) Schedule maintenance merge after batch dedup. "
            "3) After `process_pending_deduplication`, call near-dup scan on affected date/city buckets."
        ),
        "change_targets": [
            "app/services/maintenance.py::merge_near_duplicate_unique_events",
            "app/services/dedup_scan.py::pair_signal",
            "app/services/enrichment.py::process_pending_deduplication",
        ],
        "change_type": "ops",
        "priority": "high",
    },
    (
        "dedup-match",
        "near_duplicate_unique_events",
        "title_fuzzy",
    ): {
        "problem_title": "Title-similar UniqueEvents not merged",
        "solution_summary": "Align title blocking thresholds and run near-dup merge",
        "root_cause": "Title-similar UniqueEvents on same day/city were not merged",
        "mechanism": (
            "Fuzzy title match exceeds `FUZZY_TITLE_THRESHOLD` (0.80) in dedup_scan but "
            "ingest blocking or LLM match did not link them; maintenance merge not applied."
        ),
        "recommended_change": (
            "1) Run near-dup merge for the affected group. "
            "2) Align `find_candidate_unique_events` title blocking with `pair_signal` thresholds. "
            "3) Add eval cases for title_fuzzy pairs; consider lowering threshold if LLM re-run confirms match."
        ),
        "change_targets": [
            "app/services/enrichment.py::FUZZY_TITLE_THRESHOLD",
            "app/services/enrichment.py::block_by_title_fuzzy",
            "app/services/dedup_scan.py::pair_signal",
            "app/services/maintenance.py::merge_near_duplicate_unique_events",
        ],
        "change_type": "code",
        "priority": "high",
    },
    (
        "dedup-match",
        "near_duplicate_unique_events",
        "title_substring",
    ): {
        "problem_title": "Substring title duplicates not merged",
        "solution_summary": "Extend title blocking to catch substring matches",
        "root_cause": "Substring title match indicates duplicate UniqueEvents",
        "mechanism": "Titles share a common substring but events remain separate in the DB.",
        "recommended_change": (
            "Run near-dup merge; ensure `block_by_title_fuzzy` catches substring cases "
            "or add substring check to candidate blocking."
        ),
        "change_targets": [
            "app/services/enrichment.py::block_by_title_fuzzy",
            "app/services/dedup_scan.py::pair_signal",
        ],
        "change_type": "code",
        "priority": "high",
    },
    (
        "dedup-match",
        "near_duplicate_unique_events",
        "description_fuzzy",
    ): {
        "problem_title": "Description-similar UniqueEvents not merged",
        "solution_summary": "Add description blocking or scheduled near-dup merge",
        "root_cause": "Chronological descriptions match but UniqueEvents stayed separate",
        "mechanism": "Description similarity ≥ 0.55 in dedup_scan; blocking strategies may not surface these as candidates during ingest.",
        "recommended_change": (
            "Add description-based blocking in `find_candidate_unique_events` or run scheduled near-dup merge."
        ),
        "change_targets": [
            "app/services/enrichment.py::find_candidate_unique_events",
            "app/services/dedup_scan.py::pair_signal",
        ],
        "change_type": "code",
        "priority": "medium",
    },
    (
        "dedup-match",
        "matched_while_sibling_exists",
        "",
    ): {
        "problem_title": "Sibling UniqueEvents left unmerged after match",
        "solution_summary": "Merge siblings after link_raw_event_to_unique_event",
        "root_cause": "RawEvent matched one UE while a near-duplicate sibling UE still exists",
        "mechanism": (
            "LLM match linked raw event to UE A but sibling UE B (same incident) was never merged into A."
        ),
        "recommended_change": (
            "Merge sibling UniqueEvents after successful match; extend `link_raw_event_to_unique_event` "
            "to trigger near-dup scan on the matched UE's date/city bucket."
        ),
        "change_targets": [
            "app/services/enrichment.py::link_raw_event_to_unique_event",
            "app/services/maintenance.py::merge_unique_events_by_ids",
        ],
        "change_type": "code",
        "priority": "high",
    },
    (
        "dedup-cluster",
        "pending_overlap_cluster",
        "",
    ): {
        "problem_title": "Pending RawEvents not clustered by batch dedup",
        "solution_summary": "Run process_pending_deduplication and ensure worker cron",
        "root_cause": "Overlapping pending RawEvents were never clustered into a UniqueEvent",
        "mechanism": (
            "Batch dedup (`process_pending_deduplication`) did not run, hit limit, or LLM cluster "
            "returned singletons despite victim/title overlap."
        ),
        "recommended_change": (
            "1) Run `process_pending_deduplication` with higher limit for affected date/city. "
            "2) If re-run clusters correctly, add eval cases and tune `llm_cluster_events` prompt. "
            "3) Ensure worker cron processes pending queue."
        ),
        "change_targets": [
            "app/services/enrichment.py::process_pending_deduplication",
            "app/services/enrichment.py::llm_cluster_events",
            "app/services/enrichment.py::pre_cluster_by_victim_name",
        ],
        "change_type": "ops",
        "priority": "high",
    },
    (
        "classification",
        "false_negative",
        "",
    ): {
        "root_cause": "Violent-death headline classified as non-violent and discarded",
        "mechanism": "LLM or stored `is_violent_death` disagrees with pipeline progression expectation.",
        "recommended_change": (
            "Review classification prompt edge cases; add headline to eval fixtures; "
            "check if stored flag was overwritten incorrectly."
        ),
        "change_targets": [
            "app/services/classification.py::CLASSIFICATION_SYSTEM_PROMPT",
            "tests/fixtures/eval/classification_hard.json",
        ],
        "change_type": "prompt",
        "priority": "medium",
    },
    (
        "classification",
        "false_positive",
        "",
    ): {
        "root_cause": "Non-violent headline progressed past classification",
        "mechanism": "Source marked non-violent but reached extraction pipeline.",
        "recommended_change": "Tighten classification prompt; add negative examples to eval fixtures.",
        "change_targets": [
            "app/services/classification.py::CLASSIFICATION_SYSTEM_PROMPT",
            "tests/fixtures/eval/classification_hard.json",
        ],
        "change_type": "prompt",
        "priority": "medium",
    },
    (
        "classification",
        "death_keyword_discarded",
        "",
    ): {
        "root_cause": "Headline with death keywords was discarded",
        "mechanism": "Keyword heuristic suggests violent death but classification discarded the source.",
        "recommended_change": (
            "Re-run classification on sample; if LLM agrees, fix upstream discard logic or add keyword→review queue."
        ),
        "change_targets": [
            "app/services/classification.py",
            "eval/stages/classification/build.py::DEATH_KEYWORDS",
        ],
        "change_type": "prompt",
        "priority": "medium",
    },
    (
        "content-gate",
        "gate_false_negative",
        "",
    ): {
        "root_cause": "Article passed classification but content gate discarded it",
        "mechanism": "Full article available but gate marked non-incident or low quality.",
        "recommended_change": "Tune content-gate prompt; add article snippet to eval fixtures.",
        "change_targets": [
            "app/services/content_gate.py",
            "tests/fixtures/eval/content_gate_hard.json",
        ],
        "change_type": "prompt",
        "priority": "medium",
    },
    (
        "content-gate",
        "gate_false_positive",
        "",
    ): {
        "root_cause": "Non-violent article passed content gate and was extracted",
        "mechanism": "Gate approved content that should have stopped the pipeline.",
        "recommended_change": "Tighten content-gate criteria; add counterexamples to eval.",
        "change_targets": [
            "app/services/content_gate.py",
            "tests/fixtures/eval/content_gate_hard.json",
        ],
        "change_type": "prompt",
        "priority": "medium",
    },
    (
        "extraction",
        "extraction_failed",
        "",
    ): {
        "root_cause": "Extraction failed despite usable article content",
        "mechanism": "LLM extraction returned empty/invalid fields or timed out; raw_event.extraction_success=0.",
        "recommended_change": (
            "Sample failed extractions; tune extraction prompt/schema; check model timeouts and retries."
        ),
        "change_targets": [
            "app/services/extraction.py",
            "tests/fixtures/eval/extraction_hard.json",
        ],
        "change_type": "prompt",
        "priority": "high",
    },
    (
        "enrichment",
        "field_mismatch",
        "",
    ): {
        "root_cause": "UniqueEvent fields disagree with linked RawEvent(s)",
        "mechanism": (
            "Enrichment synthesis picked wrong city or victim_count vs source extractions."
        ),
        "recommended_change": (
            "Fix enrichment merge logic to prefer majority RawEvent values; add field-level eval cases."
        ),
        "change_targets": [
            "app/services/enrichment.py",
            "tests/fixtures/eval/enrichment_seed.json",
        ],
        "change_type": "code",
        "priority": "medium",
    },
    (
        "enrichment",
        "needs_enrichment_stale",
        "",
    ): {
        "root_cause": "UniqueEvent stuck with needs_enrichment=true",
        "mechanism": "Enrichment worker backlog or enrichment job failed silently.",
        "recommended_change": (
            "Run enrichment batch for affected UEs; check worker logs and retry policy."
        ),
        "change_targets": [
            "app/services/enrichment.py",
            "app/worker/tasks.py",
        ],
        "change_type": "ops",
        "priority": "low",
    },
}


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for node in self.parent:
            out[self.find(node)].append(node)
        return dict(out)


def _slug(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len] or "cluster"


def _sub_signal(candidate: AnomalyCandidate) -> str:
    snap = candidate.prod_snapshot
    if candidate.stage == "dedup-match" and candidate.signal == "near_duplicate_unique_events":
        return str(snap.get("signal") or "")
    return ""


def _lookup_template(stage: str, signal: str, sub_signal: str) -> DiagnosisTemplate:
    key = (stage, signal, sub_signal)
    if key in DIAGNOSIS:
        return DIAGNOSIS[key]
    fallback = (stage, signal, "")
    if fallback in DIAGNOSIS:
        return DIAGNOSIS[fallback]
    return {
        "problem_title": f"{stage.replace('-', ' ').title()}: {signal}",
        "solution_summary": f"Investigate and fix {stage} for signal `{signal}`",
        "root_cause": f"Pipeline anomaly: {signal}",
        "mechanism": "Detected by production heuristics; manual triage required.",
        "recommended_change": f"Investigate {stage} stage for signal `{signal}`.",
        "change_targets": [f"app/services/{stage.replace('-', '_')}.py"],
        "change_type": "code",
        "priority": "medium",
    }


def _refine_from_verification(
    template: DiagnosisTemplate,
    verified_results: list[VerificationResult],
) -> DiagnosisTemplate:
    out = dict(template)
    if not verified_results:
        return out

    confirmed = [r for r in verified_results if r.verified]
    if not confirmed:
        out["mechanism"] = (
            f"{out['mechanism']} Verification re-run did NOT confirm "
            f"({len(verified_results) - len(confirmed)}/{len(verified_results)} failed) — "
            "may be false positives; review before changing algorithm."
        )
        out["priority"] = "low"
        return out

    stage = confirmed[0].stage
    if stage == "dedup-match":
        confidences = [
            r.rerun_outcome.get("confidence")
            for r in confirmed
            if r.rerun_outcome.get("confidence") is not None
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else None
        out["mechanism"] = (
            f"{out['mechanism']} Re-run confirms LLM would match "
            f"({len(confirmed)}/{len(verified_results)} verified"
            + (f", avg confidence {avg_conf:.2f}" if avg_conf else "")
            + ") — prod state is stale; merge/link not applied at ingest time."
        )
        if out.get("change_type") == "code":
            out["recommended_change"] = (
                f"{out['recommended_change']} "
                "Since re-run succeeds, prioritize ops merge + post-ingest near-dup scan over prompt changes."
            )
    elif stage == "dedup-cluster":
        out["mechanism"] = (
            f"{out['mechanism']} Re-run confirms events should cluster "
            f"({len(confirmed)}/{len(verified_results)} verified) — batch job likely not run or under-limited."
        )
    elif stage in ("classification", "content-gate", "extraction"):
        out["mechanism"] = (
            f"{out['mechanism']} Re-run confirms current model reproduces the prod mistake "
            f"({len(confirmed)}/{len(verified_results)}) — prompt or model change needed."
        )
        out["change_type"] = "prompt"

    return out


def _solution_key(candidate: AnomalyCandidate) -> tuple[str, str, str]:
    return (candidate.stage, candidate.signal, _sub_signal(candidate))


def _fix_id_for_solution(stage: str, signal: str, sub_signal: str) -> str:
    parts = [stage.replace("-", "_"), sub_signal or signal]
    return f"fix-{_slug('-'.join(p for p in parts if p), 60)}"


def _aggregate_dedup_match_affected(members: list[AnomalyCandidate]) -> list[AffectedGroup]:
    """Within one solution cluster, list each incident (city+date+connected UEs)."""
    buckets: dict[tuple[str, str], list[AnomalyCandidate]] = defaultdict(list)
    for c in members:
        snap = c.prod_snapshot
        city = str(snap.get("city") or "?")
        day = str(snap.get("event_date") or "")[:10] or "?"
        buckets[(city, day)].append(c)

    affected: list[AffectedGroup] = []
    for (city, day), bucket in sorted(buckets.items()):
        uf = _UnionFind()
        for c in bucket:
            snap = c.prod_snapshot
            uf.union(int(snap["id_a"]), int(snap["id_b"]))

        by_root: dict[int, list[AnomalyCandidate]] = defaultdict(list)
        for c in bucket:
            root = uf.find(int(c.prod_snapshot["id_a"]))
            by_root[root].append(c)

        for root, component in by_root.items():
            ue_ids = sorted(
                {int(m.prod_snapshot["id_a"]) for m in component}
                | {int(m.prod_snapshot["id_b"]) for m in component}
            )
            affected.append(
                AffectedGroup(
                    label=f"{city} {day}",
                    city=city if city != "?" else None,
                    event_date=day if day != "?" else None,
                    unique_event_ids=ue_ids,
                    suggested_survivor_id=min(ue_ids) if ue_ids else None,
                    pair_count=len(component),
                    candidate_ids=[c.candidate_id for c in component],
                )
            )
    return affected


def _aggregate_dedup_cluster_affected(members: list[AnomalyCandidate]) -> list[AffectedGroup]:
    affected: list[AffectedGroup] = []
    for c in members:
        snap = c.prod_snapshot
        city = str(snap.get("city") or "?")
        day = str(snap.get("event_date") or "")[:10] or "?"
        raw_ids = list(snap.get("raw_event_ids") or c.input.get("raw_event_ids") or [])
        affected.append(
            AffectedGroup(
                label=f"{city} {day}",
                city=city if city != "?" else None,
                event_date=day if day != "?" else None,
                raw_event_ids=raw_ids,
                pair_count=len(raw_ids),
                candidate_ids=[c.candidate_id],
            )
        )
    return sorted(affected, key=lambda g: (g.event_date or "", g.city or ""))


def _aggregate_enrichment_affected(members: list[AnomalyCandidate]) -> list[AffectedGroup]:
    affected: list[AffectedGroup] = []
    for c in members:
        ue_id = c.input.get("unique_event_id") or c.prod_snapshot.get("unique_event_id")
        affected.append(
            AffectedGroup(
                label=f"UE {ue_id}",
                unique_event_ids=[int(ue_id)] if ue_id else [],
                candidate_ids=[c.candidate_id],
            )
        )
    return affected


def _aggregate_generic_affected(members: list[AnomalyCandidate]) -> list[AffectedGroup]:
    affected: list[AffectedGroup] = []
    for c in members:
        label = c.candidate_id
        if c.stage == "classification":
            headline = (c.prod_snapshot.get("headline") or "")[:60]
            label = f"Source — {headline}…" if headline else c.candidate_id
        elif c.stage == "extraction":
            title = (c.prod_snapshot.get("title") or c.input.get("headline") or "")[:60]
            label = f"RawEvent — {title}…" if title else c.candidate_id
        affected.append(AffectedGroup(label=label, candidate_ids=[c.candidate_id]))
    return affected


def _aggregate_affected(stage: str, signal: str, members: list[AnomalyCandidate]) -> list[AffectedGroup]:
    if stage == "dedup-match" and signal == "near_duplicate_unique_events":
        return _aggregate_dedup_match_affected(members)
    if stage == "dedup-cluster":
        return _aggregate_dedup_cluster_affected(members)
    if stage == "enrichment":
        return _aggregate_enrichment_affected(members)
    return _aggregate_generic_affected(members)


def _impact_summary(affected: list[AffectedGroup], stage: str) -> str:
    if not affected:
        return "—"
    if stage == "dedup-match":
        ue_total = len({uid for g in affected for uid in g.unique_event_ids})
        return f"{len(affected)} incidents · {ue_total} duplicate UEs · {sum(g.pair_count for g in affected)} pairs"
    if stage == "dedup-cluster":
        raw_total = sum(len(g.raw_event_ids) for g in affected)
        return f"{len(affected)} pending clusters · {raw_total} raw events"
    if stage == "enrichment":
        return f"{len(affected)} unique events"
    return f"{len(affected)} cases"


def build_diagnosis(
    candidates: list[AnomalyCandidate],
    verified_by_id: dict[str, VerificationResult] | None = None,
) -> DiagnosisReport:
    verified_by_id = verified_by_id or {}
    by_solution: dict[tuple[str, str, str], list[AnomalyCandidate]] = defaultdict(list)
    for c in candidates:
        by_solution[_solution_key(c)].append(c)

    clusters: list[FixCluster] = []

    for (stage, signal, sub_signal), members in by_solution.items():
        template = _lookup_template(stage, signal, sub_signal)
        member_verifications = [
            verified_by_id[c.candidate_id] for c in members if c.candidate_id in verified_by_id
        ]
        refined = _refine_from_verification(template, member_verifications)
        verified_count = sum(1 for v in member_verifications if v.verified)
        affected = _aggregate_affected(stage, signal, members)

        all_ue_ids = sorted({uid for g in affected for uid in g.unique_event_ids})
        all_raw_ids = sorted({rid for g in affected for rid in g.raw_event_ids})

        problem = refined.get("problem_title") or refined["root_cause"]
        solution = refined.get("solution_summary") or refined["recommended_change"][:120]

        clusters.append(
            FixCluster(
                fix_id=_fix_id_for_solution(stage, signal, sub_signal),
                stage=stage,  # type: ignore[arg-type]
                signal=signal,
                sub_signal=sub_signal,
                title=problem,
                problem=problem,
                solution=solution,
                root_cause=refined["root_cause"],
                mechanism=refined["mechanism"],
                recommended_change=refined["recommended_change"],
                change_targets=list(refined.get("change_targets") or []),
                change_type=refined.get("change_type", "code"),
                priority=refined.get("priority", "medium"),
                candidate_ids=[c.candidate_id for c in members],
                example_ids=[c.candidate_id for c in members[:3]],
                affected=affected,
                evidence=_impact_summary(affected, stage),
                verified_count=verified_count,
                total_count=len(members),
                context={
                    "impact_summary": _impact_summary(affected, stage),
                    "incident_count": len(affected),
                    "unique_event_ids": all_ue_ids,
                    "raw_event_ids": all_raw_ids,
                },
            )
        )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    clusters.sort(key=lambda c: (priority_order.get(c.priority, 9), -c.total_count, c.stage))

    clusters = analyze_report_clusters(clusters, verified_by_id)

    return DiagnosisReport(
        meta={"cluster_count": len(clusters), "candidate_count": len(candidates)},
        clusters=clusters,
    )
