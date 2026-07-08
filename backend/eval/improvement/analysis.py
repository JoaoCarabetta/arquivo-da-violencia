"""Root-cause hypotheses, scored solution options, and eval recommendations."""

from __future__ import annotations

from typing import Any

from eval.improvement.schemas import (
    AnomalyCandidate,
    EvalRecommendation,
    FixCluster,
    RootCauseHypothesis,
    SolutionOption,
    VerificationResult,
)

# Weighted score = sum(dimension * weight). Each dimension is 0–10.
SCORE_WEIGHTS: dict[str, float] = {
    "effectiveness": 0.35,
    "permanence": 0.25,
    "effort_inverse": 0.15,
    "risk_inverse": 0.15,
    "eval_signal": 0.10,
}


def weighted_score(scores: dict[str, float]) -> float:
    return round(
        sum(scores.get(k, 0) * w for k, w in SCORE_WEIGHTS.items()),
        2,
    )


AnalysisTemplate = dict[str, Any]

# Keyed by (stage, signal, sub_signal) — same as diagnose.py
ANALYSIS: dict[tuple[str, str, str], AnalysisTemplate] = {
    (
        "dedup-match",
        "near_duplicate_unique_events",
        "victim_name",
    ): {
        "hypotheses": [
            {
                "hypothesis_id": "maintenance-not-scheduled",
                "description": "Near-dup maintenance merge never runs after ingest/batch dedup",
                "base_likelihood": 0.40,
                "evidence_for": "pair_signal detects victim overlap in prod but UEs remain separate; no merge audit trail",
                "how_to_confirm": "Check prod cron/worker logs for merge_near_duplicate_unique_events; grep maintenance audit",
            },
            {
                "hypothesis_id": "batch-creates-duplicate-ues",
                "description": "Batch clustering creates a new UniqueEvent per source without merging into existing UEs",
                "base_likelihood": 0.35,
                "evidence_for": "Affected UEs often have source_count=1 each — same victim, different headlines",
                "how_to_confirm": "Trace ingest path for affected raw_event_ids; check if find_candidate_unique_events returned existing UE",
            },
            {
                "hypothesis_id": "llm-match-rejected",
                "description": "LLM match returned no-match or confidence below threshold at ingest time",
                "base_likelihood": 0.15,
                "evidence_for": "Possible when victim names differ in wording across sources",
                "how_to_confirm": "Re-run verify on sample pairs; compare confidence vs LLM_MATCH_CONFIDENCE_THRESHOLD (0.6)",
            },
            {
                "hypothesis_id": "ingest-order-timing",
                "description": "Second source arrived before first UE had victim_name populated",
                "base_likelihood": 0.10,
                "evidence_for": "Rare; blocking uses extraction_data victim names",
                "how_to_confirm": "Compare created_at on raw_events vs enrichment timestamps for affected UEs",
            },
        ],
        "solutions": [
            {
                "option_id": "ops-merge-now-plus-cron",
                "name": "Ops: merge existing dupes + schedule maintenance cron",
                "description": (
                    "Run `merge_near_duplicate_unique_events` on prod/staging immediately, "
                    "then add cron after batch dedup."
                ),
                "change_type": "ops",
                "change_targets": [
                    "app/services/maintenance.py::merge_near_duplicate_unique_events",
                    "scripts/check-pipeline-health.sh",
                ],
                "scores": {
                    "effectiveness": 8.0,
                    "permanence": 5.0,
                    "effort_inverse": 9.5,
                    "risk_inverse": 8.5,
                    "eval_signal": 4.0,
                },
                "pros": "Fast heal of 20 duplicate UEs; low code risk; reversible via DB backup",
                "cons": "Does not stop new dupes if ingest path unchanged; ops-only",
                "requires_eval": False,
                "eval_rationale": "Ops merge heals data but does not change algorithm — eval cannot prevent missed cron",
            },
            {
                "option_id": "code-post-dedup-near-dup-scan",
                "name": "Code: post-dedup near-dup scan hook",
                "description": (
                    "After `process_pending_deduplication` and after `link_raw_event_to_unique_event`, "
                    "run pair_signal scan on the date/city bucket and auto-merge."
                ),
                "change_type": "code",
                "change_targets": [
                    "app/services/enrichment.py::process_pending_deduplication",
                    "app/services/enrichment.py::link_raw_event_to_unique_event",
                    "app/services/dedup_scan.py::pair_signal",
                    "app/services/maintenance.py::merge_unique_events_by_ids",
                ],
                "scores": {
                    "effectiveness": 9.0,
                    "permanence": 9.5,
                    "effort_inverse": 6.0,
                    "risk_inverse": 7.0,
                    "eval_signal": 9.0,
                },
                "pros": "Prevents recurrence; uses same heuristic that detected the bug; testable",
                "cons": "Medium dev effort; wrong merge is high-impact — needs eval guard",
                "requires_eval": True,
                "eval_rationale": (
                    "Eval must lock victim_name/title pairs that should merge AND pairs that must stay "
                    "separate — otherwise auto-merge regresses legitimate multi-victim days"
                ),
                "eval_fixture": "tests/fixtures/eval/dedup_match_hard.json",
            },
            {
                "option_id": "code-lower-match-threshold",
                "name": "Code: lower LLM_MATCH_CONFIDENCE_THRESHOLD",
                "description": "Reduce threshold below 0.6 so borderline LLM matches link at ingest.",
                "change_type": "config",
                "change_targets": [
                    "app/services/enrichment.py::LLM_MATCH_CONFIDENCE_THRESHOLD",
                    "app/services/enrichment.py::llm_match_to_unique_event",
                ],
                "scores": {
                    "effectiveness": 5.5,
                    "permanence": 6.0,
                    "effort_inverse": 9.0,
                    "risk_inverse": 4.0,
                    "eval_signal": 8.0,
                },
                "pros": "One-line config change; helps ingest-time linking",
                "cons": "High false-merge risk across city/day; does not heal existing 20 dupes",
                "requires_eval": True,
                "eval_rationale": "Threshold change affects all matches — dedup_match eval is mandatory before deploy",
                "eval_fixture": "tests/fixtures/eval/dedup_match_hard.json",
            },
            {
                "option_id": "prompt-dedup-match-tuning",
                "name": "Prompt: tune MATCH_SYSTEM_PROMPT for victim-first linking",
                "description": "Strengthen victim-name priority in dedup match LLM prompt.",
                "change_type": "prompt",
                "change_targets": [
                    "app/services/enrichment.py::MATCH_SYSTEM_PROMPT",
                ],
                "scores": {
                    "effectiveness": 6.5,
                    "permanence": 7.0,
                    "effort_inverse": 7.0,
                    "risk_inverse": 5.5,
                    "eval_signal": 9.5,
                },
                "pros": "Targets root LLM behavior; pairs well with eval iteration",
                "cons": "Slow to validate; does not heal existing dupes; model-dependent",
                "requires_eval": True,
                "eval_rationale": "Prompt changes require before/after dedup_match run — only eval catches wrong merges",
                "eval_fixture": "tests/fixtures/eval/dedup_match_hard.json",
            },
        ],
        "eval_default": {
            "add_to_eval": True,
            "priority": "required",
            "rationale": (
                "Prod found victim_name duplicates (Celeste Martins, Aarão Reis) not covered by current "
                "dedup_match_hard.json. Auto-merge or threshold changes without eval risk merging "
                "distinct same-day incidents in the same city."
            ),
            "fixture_path": "tests/fixtures/eval/dedup_match_hard.json",
            "suggested_cases": [
                "Salvador feminicide — Celeste Martins pairs (merge=true)",
                "Belo Horizonte Aarão Reis 9722/9723/9730 (merge=true)",
                "Porto Velho Caio Francisco pair (merge=true)",
            ],
        },
    },
    (
        "dedup-cluster",
        "pending_overlap_cluster",
        "",
    ): {
        "hypotheses": [
            {
                "hypothesis_id": "batch-job-not-running",
                "description": "process_pending_deduplication worker/cron is not running or is failing silently",
                "base_likelihood": 0.38,
                "evidence_for": "21 raw events stuck in deduplication_status=pending with obvious overlap",
                "how_to_confirm": "Check worker logs and pipeline health script; query count(*) WHERE status=pending",
            },
            {
                "hypothesis_id": "batch-limit-backlog",
                "description": "Batch limit (default 200) is exhausted before these events are reached",
                "base_likelihood": 0.28,
                "evidence_for": "Pending events span multiple days — older pending may starve",
                "how_to_confirm": "Compare pending queue depth vs limit; check event_date ordering in batch query",
            },
            {
                "hypothesis_id": "llm-cluster-singletons",
                "description": "llm_cluster_events returns one-event clusters despite overlap",
                "base_likelihood": 0.22,
                "evidence_for": "pre_cluster would group but LLM may split on headline differences",
                "how_to_confirm": "Re-run verify with llm_cluster_events on sample cluster (Sabará, Contagem)",
            },
            {
                "hypothesis_id": "pre-cluster-gap",
                "description": "pre_cluster_by_victim_name misses cases without extracted victim names",
                "base_likelihood": 0.12,
                "evidence_for": "Some pending clusters match on title only",
                "how_to_confirm": "Inspect extraction_data victim names on pending raw_event_ids",
            },
        ],
        "solutions": [
            {
                "option_id": "ops-run-batch-now",
                "name": "Ops: run process_pending_deduplication now with higher limit",
                "description": "Immediate batch run on prod/staging pending queue (limit 500+).",
                "change_type": "ops",
                "change_targets": [
                    "app/services/enrichment.py::process_pending_deduplication",
                ],
                "scores": {
                    "effectiveness": 8.5,
                    "permanence": 3.0,
                    "effort_inverse": 10.0,
                    "risk_inverse": 9.0,
                    "eval_signal": 3.0,
                },
                "pros": "Clears 21 pending raws immediately; zero code deploy",
                "cons": "One-time; queue fills again if cron broken",
                "requires_eval": False,
                "eval_rationale": "Ops batch run does not change algorithm — eval not required for one-off heal",
            },
            {
                "option_id": "ops-cron-monitoring",
                "name": "Ops: fix worker cron + pipeline health alerts",
                "description": "Ensure pending dedup runs on schedule; alert when pending count grows.",
                "change_type": "ops",
                "change_targets": [
                    "app/worker/tasks.py",
                    "scripts/check-pipeline-health.sh",
                ],
                "scores": {
                    "effectiveness": 7.5,
                    "permanence": 8.5,
                    "effort_inverse": 8.0,
                    "risk_inverse": 9.5,
                    "eval_signal": 2.0,
                },
                "pros": "Prevents backlog recurrence; observable",
                "cons": "Does not fix LLM clustering quality",
                "requires_eval": False,
                "eval_rationale": "Scheduling fix is ops — eval does not test cron reliability",
            },
            {
                "option_id": "code-stronger-pre-cluster",
                "name": "Code: strengthen pre_cluster_by_victim_name + title overlap before LLM",
                "description": (
                    "Expand pre_cluster to use title fuzzy match (same as detect heuristic) "
                    "before calling llm_cluster_events."
                ),
                "change_type": "code",
                "change_targets": [
                    "app/services/enrichment.py::pre_cluster_by_victim_name",
                    "app/services/enrichment.py::process_pending_deduplication",
                ],
                "scores": {
                    "effectiveness": 8.5,
                    "permanence": 9.0,
                    "effort_inverse": 6.5,
                    "risk_inverse": 7.5,
                    "eval_signal": 9.5,
                },
                "pros": "Reduces LLM cost; aligns batch with detect heuristic; durable fix",
                "cons": "Wrong pre-cluster merges distinct incidents — needs eval",
                "requires_eval": True,
                "eval_rationale": (
                    "No dedup_cluster fixture exists today. Prod Sabará/Contagem/Cuiabá clusters "
                    "must become labeled cases before changing pre_cluster logic."
                ),
                "eval_fixture": "tests/fixtures/eval/dedup_cluster_seed.json",
            },
            {
                "option_id": "prompt-cluster-tuning",
                "name": "Prompt: tune llm_cluster_events for same-day headline variance",
                "description": "Adjust cluster prompt to merge same-victim/same-location despite headline differences.",
                "change_type": "prompt",
                "change_targets": [
                    "app/services/enrichment.py::llm_cluster_events",
                ],
                "scores": {
                    "effectiveness": 7.0,
                    "permanence": 7.5,
                    "effort_inverse": 7.0,
                    "risk_inverse": 5.0,
                    "eval_signal": 10.0,
                },
                "pros": "Handles edge cases pre_cluster misses",
                "cons": "Expensive to run; prompt regressions are subtle",
                "requires_eval": True,
                "eval_rationale": "Cluster prompt changes MUST have dedup_cluster eval — no fixture file exists yet",
                "eval_fixture": "tests/fixtures/eval/dedup_cluster_seed.json",
            },
        ],
        "eval_default": {
            "add_to_eval": True,
            "priority": "required",
            "rationale": (
                "dedup_cluster_seed.json does not exist. Any code/prompt change to clustering "
                "is untestable in CI today. Prod pending clusters (Sabará 5 raws, Contagem feminicide) "
                "are ideal seed cases."
            ),
            "fixture_path": "tests/fixtures/eval/dedup_cluster_seed.json",
            "suggested_cases": [
                "Sabará 2026-07-06 — 5 pending raws VILA MICHEL/SABARÁ (cluster together)",
                "Contagem 2026-07-04 — 4 CARAJÁS feminicide raws (cluster together)",
                "Cuiabá 2026-07-07 — 3 casa abandonada raws (cluster together)",
            ],
        },
    },
    (
        "enrichment",
        "field_mismatch",
        "",
    ): {
        "hypotheses": [
            {
                "hypothesis_id": "enrichment-llm-wrong-aggregate",
                "description": "Enrichment LLM synthesized wrong victim_count when sources disagree",
                "base_likelihood": 0.45,
                "evidence_for": "UE victim_count=2 but some linked raws extracted victim_count=1",
                "how_to_confirm": "Compare enrichment reasoning/logs for UE 9703 and 9731",
            },
            {
                "hypothesis_id": "merge-no-majority-vote",
                "description": "Field merge logic picks first/stale raw value instead of majority",
                "base_likelihood": 0.35,
                "evidence_for": "Multiple raws with mixed counts linked to same UE",
                "how_to_confirm": "Read enrichment field merge code path for victim_count",
            },
            {
                "hypothesis_id": "stale-enrichment-after-new-raw",
                "description": "New raw linked but UE not re-enriched",
                "base_likelihood": 0.20,
                "evidence_for": "needs_enrichment flag may have cleared prematurely",
                "how_to_confirm": "Check updated_at ordering on UE vs latest raw_event link",
            },
        ],
        "solutions": [
            {
                "option_id": "code-majority-field-merge",
                "name": "Code: majority/median vote on victim_count and city from linked raws",
                "description": (
                    "Deterministic merge: victim_count = mode of raw extractions; "
                    "city = mode or highest-confidence raw."
                ),
                "change_type": "code",
                "change_targets": [
                    "app/services/enrichment.py",
                ],
                "scores": {
                    "effectiveness": 9.0,
                    "permanence": 9.5,
                    "effort_inverse": 6.0,
                    "risk_inverse": 7.5,
                    "eval_signal": 9.0,
                },
                "pros": "Deterministic; fixes 9703/9731 pattern directly; testable",
                "cons": "Edge cases when sources truly disagree on distinct victims",
                "requires_eval": True,
                "eval_rationale": "Field merge rules need labeled expected values per UE",
                "eval_fixture": "tests/fixtures/eval/enrichment_seed.json",
            },
            {
                "option_id": "prompt-enrichment-fields",
                "name": "Prompt: enrichment instructions for victim_count reconciliation",
                "description": "Tell enrichment LLM to prefer majority raw extraction values.",
                "change_type": "prompt",
                "change_targets": [
                    "app/services/enrichment.py",
                ],
                "scores": {
                    "effectiveness": 6.0,
                    "permanence": 6.5,
                    "effort_inverse": 7.5,
                    "risk_inverse": 5.0,
                    "eval_signal": 8.5,
                },
                "pros": "Quick to try",
                "cons": "Non-deterministic; LLM may still hallucinate counts",
                "requires_eval": True,
                "eval_rationale": "Prompt-only fix still needs enrichment eval to verify field accuracy",
                "eval_fixture": "tests/fixtures/eval/enrichment_seed.json",
            },
            {
                "option_id": "ops-re-enrich-affected",
                "name": "Ops: re-run enrichment on UE 9703 and 9731",
                "description": "Trigger enrichment batch on affected unique events only.",
                "change_type": "ops",
                "change_targets": [
                    "app/services/enrichment.py",
                    "app/worker/tasks.py",
                ],
                "scores": {
                    "effectiveness": 7.0,
                    "permanence": 2.0,
                    "effort_inverse": 9.5,
                    "risk_inverse": 8.0,
                    "eval_signal": 2.0,
                },
                "pros": "May fix these 2 UEs immediately",
                "cons": "Same bug will recur on next multi-source UE without code change",
                "requires_eval": False,
                "eval_rationale": "One-off re-enrich does not change algorithm",
            },
        ],
        "eval_default": {
            "add_to_eval": True,
            "priority": "recommended",
            "rationale": (
                "enrichment_seed.json does not exist. Field-level eval (victim_count, city) "
                "is needed before changing merge logic — but only 2 prod cases so far, "
                "so priority is recommended not required unless code path changes."
            ),
            "fixture_path": "tests/fixtures/eval/enrichment_seed.json",
            "suggested_cases": [
                "UE 9703 — 3 raws with mixed victim_count 1/2 (expected UE victim_count=?)",
                "UE 9731 — 2 raws with victim_count 1 vs 2",
            ],
        },
    },
}


def _lookup_analysis(stage: str, signal: str, sub_signal: str) -> AnalysisTemplate:
    key = (stage, signal, sub_signal)
    if key in ANALYSIS:
        return ANALYSIS[key]
    fallback = (stage, signal, "")
    if fallback in ANALYSIS:
        return ANALYSIS[fallback]
    return {
        "hypotheses": [
            {
                "hypothesis_id": "unknown",
                "description": f"Pipeline anomaly at {stage}/{signal}",
                "base_likelihood": 1.0,
                "evidence_for": "Detected by prod heuristics",
                "how_to_confirm": "Manual triage",
            }
        ],
        "solutions": [
            {
                "option_id": "manual-triage",
                "name": "Manual investigation",
                "description": f"Investigate {stage} for signal `{signal}`",
                "change_type": "code",
                "change_targets": [f"app/services/{stage.replace('-', '_')}.py"],
                "scores": {
                    "effectiveness": 5.0,
                    "permanence": 5.0,
                    "effort_inverse": 5.0,
                    "risk_inverse": 5.0,
                    "eval_signal": 5.0,
                },
                "pros": "Placeholder",
                "cons": "No automated analysis template",
                "requires_eval": False,
                "eval_rationale": "Define analysis template for this signal",
            }
        ],
        "eval_default": {
            "add_to_eval": False,
            "priority": "optional",
            "rationale": "No analysis template — triage manually before adding eval",
            "fixture_path": None,
            "suggested_cases": [],
        },
    }


def _adjust_likelihoods(
    hypotheses: list[RootCauseHypothesis],
    cluster: FixCluster,
    verified: list[VerificationResult],
) -> list[RootCauseHypothesis]:
    """Re-weight hypotheses using cluster evidence and verification."""
    if not hypotheses:
        return hypotheses

    adjusted: list[tuple[float, RootCauseHypothesis]] = []
    for h in hypotheses:
        likelihood = h.likelihood
        if cluster.stage == "dedup-match" and h.hypothesis_id == "maintenance-not-scheduled":
            if cluster.total_count >= 10:
                likelihood += 0.08
        if cluster.stage == "dedup-match" and h.hypothesis_id == "llm-match-rejected":
            confirmed = [v for v in verified if v.verified]
            if confirmed:
                likelihood += 0.15
            else:
                likelihood -= 0.05
        if cluster.stage == "dedup-cluster" and h.hypothesis_id == "batch-job-not-running":
            if cluster.total_count >= 5:
                likelihood += 0.10
        adjusted.append((max(0.05, likelihood), h))

    total = sum(x[0] for x in adjusted) or 1.0
    return [
        h.model_copy(update={"likelihood": round(lik / total, 2)})
        for lik, h in adjusted
    ]


def _adjust_solution_scores(
    options: list[SolutionOption],
    verified: list[VerificationResult],
) -> list[SolutionOption]:
    """Boost ops merge when verify confirms LLM would match (stale state)."""
    confirmed = [v for v in verified if v.verified]
    if not confirmed:
        return options

    out: list[SolutionOption] = []
    for opt in options:
        scores = dict(opt.scores)
        if opt.option_id == "ops-merge-now-plus-cron" and confirmed:
            scores["effectiveness"] = min(10.0, scores.get("effectiveness", 0) + 1.0)
        if opt.option_id == "code-lower-match-threshold" and confirmed:
            scores["effectiveness"] = min(10.0, scores.get("effectiveness", 0) + 0.5)
            scores["risk_inverse"] = max(0.0, scores.get("risk_inverse", 0) - 1.0)
        out.append(
            opt.model_copy(
                update={
                    "scores": scores,
                    "weighted_score": weighted_score(scores),
                }
            )
        )
    return out


def _build_hypotheses(template: AnalysisTemplate) -> list[RootCauseHypothesis]:
    return [
        RootCauseHypothesis(
            hypothesis_id=h["hypothesis_id"],
            description=h["description"],
            likelihood=h["base_likelihood"],
            evidence_for=h["evidence_for"],
            how_to_confirm=h["how_to_confirm"],
        )
        for h in template.get("hypotheses", [])
    ]


def _build_solutions(template: AnalysisTemplate) -> list[SolutionOption]:
    options: list[SolutionOption] = []
    for s in template.get("solutions", []):
        scores = dict(s["scores"])
        options.append(
            SolutionOption(
                option_id=s["option_id"],
                name=s["name"],
                description=s["description"],
                change_type=s["change_type"],
                change_targets=list(s.get("change_targets") or []),
                scores=scores,
                weighted_score=weighted_score(scores),
                pros=s.get("pros", ""),
                cons=s.get("cons", ""),
                requires_eval=bool(s.get("requires_eval", False)),
                eval_rationale=s.get("eval_rationale", ""),
                eval_fixture=s.get("eval_fixture"),
            )
        )
    return sorted(options, key=lambda o: o.weighted_score, reverse=True)


def _build_eval_recommendation(
    template: AnalysisTemplate,
    elected: SolutionOption | None,
    cluster: FixCluster,
) -> EvalRecommendation:
    default = template.get("eval_default") or {}
    add = default.get("add_to_eval", False)
    priority = default.get("priority", "optional")
    rationale = default.get("rationale", "")

    if elected and elected.requires_eval:
        add = True
        if priority == "optional":
            priority = "recommended"
        rationale = (
            f"Elected solution `{elected.option_id}` requires eval: {elected.eval_rationale}"
        )

    if elected and elected.change_type == "ops" and not elected.requires_eval:
        add = default.get("add_to_eval", False)
        if add:
            rationale = (
                f"{rationale} Ops-only elected fix does not require eval for deploy, "
                "but adding prod cases is still recommended before code changes."
            )
        else:
            priority = "optional"
            rationale = (
                "Ops-only fix elected — eval not required for one-time heal. "
                "Add eval before any code/prompt follow-up."
            )

    return EvalRecommendation(
        add_to_eval=add,
        priority=priority,
        rationale=rationale,
        suggested_cases=list(default.get("suggested_cases") or []),
        fixture_path=default.get("fixture_path"),
        elected_requires_eval=elected.requires_eval if elected else False,
    )


def analyze_cluster(
    cluster: FixCluster,
    verified: list[VerificationResult],
) -> FixCluster:
    """Attach hypotheses, scored solutions, elected winner, and eval recommendation."""
    template = _lookup_analysis(cluster.stage, cluster.signal, cluster.sub_signal)
    hypotheses = _adjust_likelihoods(
        _build_hypotheses(template), cluster, verified
    )
    solutions = _adjust_solution_scores(_build_solutions(template), verified)
    elected = solutions[0] if solutions else None

    eval_rec = _build_eval_recommendation(template, elected, cluster)

    return cluster.model_copy(
        update={
            "root_causes": hypotheses,
            "solutions": solutions,
            "elected_solution_id": elected.option_id if elected else "",
            "solution": elected.name if elected else cluster.solution,
            "recommended_change": elected.description if elected else cluster.recommended_change,
            "change_type": elected.change_type if elected else cluster.change_type,
            "change_targets": elected.change_targets if elected else cluster.change_targets,
            "eval_recommendation": eval_rec,
            "context": {
                **cluster.context,
                "elected_weighted_score": elected.weighted_score if elected else None,
                "score_weights": SCORE_WEIGHTS,
            },
        }
    )


def analyze_report_clusters(
    clusters: list[FixCluster],
    verified_by_id: dict[str, VerificationResult],
) -> list[FixCluster]:
    out: list[FixCluster] = []
    for cluster in clusters:
        verified = [
            verified_by_id[cid]
            for cid in cluster.candidate_ids
            if cid in verified_by_id
        ]
        out.append(analyze_cluster(cluster, verified))
    return out
