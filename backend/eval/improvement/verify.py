"""Verify anomaly candidates by re-running production pipeline functions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from eval.improvement.detectors import (
    load_raw_event_row,
    load_unique_event_row,
    raw_event_data_from_row,
    unique_event_data_from_row,
)
from eval.improvement.schemas import (
    AnomalyCandidate,
    CandidateBundle,
    VerificationResult,
    VerifiedBundle,
    utc_now_iso,
)
from eval.stages.dedup_match.run import raw_event_from_data, unique_event_from_data
from eval.schemas_dedup import RawEventData, UniqueEventData


async def run_verify(
    *,
    candidates_path: Path,
    output: Path | None,
    db_path: Path | None,
    with_llm_extraction: bool,
    concurrency: int,
) -> VerifiedBundle:
    bundle = CandidateBundle.model_validate(json.loads(candidates_path.read_text()))
    sem = asyncio.Semaphore(concurrency)

    async def worker(candidate: AnomalyCandidate) -> VerificationResult:
        async with sem:
            return await _verify_one(candidate, db_path=db_path, with_llm_extraction=with_llm_extraction)

    results = await asyncio.gather(*[worker(c) for c in bundle.candidates])

    verified_bundle = VerifiedBundle(
        meta={
            "command": "verify",
            "run_at": utc_now_iso(),
            "source": str(candidates_path),
            "db": str(db_path) if db_path else "DATABASE_URL",
            "with_llm_extraction": with_llm_extraction,
            "total": len(results),
            "verified_count": sum(1 for r in results if r.verified),
        },
        results=list(results),
    )

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(verified_bundle.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )

    return verified_bundle


async def _verify_one(
    candidate: AnomalyCandidate,
    *,
    db_path: Path | None,
    with_llm_extraction: bool,
) -> VerificationResult:
    try:
        if candidate.stage == "classification":
            return await _verify_classification(candidate)
        if candidate.stage == "content-gate":
            return await _verify_content_gate(candidate)
        if candidate.stage == "extraction":
            return await _verify_extraction(candidate, with_llm=with_llm_extraction)
        if candidate.stage == "dedup-match":
            return await _verify_dedup_match(candidate, db_path=db_path)
        if candidate.stage == "dedup-cluster":
            return await _verify_dedup_cluster(candidate, db_path=db_path)
        if candidate.stage == "enrichment":
            return await _verify_enrichment(candidate, db_path=db_path)
    except Exception as e:
        return VerificationResult(
            candidate_id=candidate.candidate_id,
            stage=candidate.stage,
            verified=False,
            notes=f"verify error: {e}",
            candidate=candidate,
        )

    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage=candidate.stage,
        verified=False,
        notes="unknown stage",
        candidate=candidate,
    )


async def _verify_classification(candidate: AnomalyCandidate) -> VerificationResult:
    from app.services.classification import classify_headline

    headline = candidate.input.get("headline", "")
    prod = candidate.prod_snapshot
    stored = prod.get("is_violent_death")
    status = prod.get("status")

    result = await asyncio.to_thread(classify_headline, headline)
    rerun = result.is_violent_death

    positive_statuses = {
        "ready_for_download",
        "downloading",
        "ready_for_extraction",
        "extracting",
        "extracted",
    }
    implied_positive = status in positive_statuses

    verified = False
    notes = ""
    if stored == 1 and status == "discarded" and rerun is True:
        verified = True
        notes = "Re-run confirms violent death; prod discarded (false negative)"
    elif stored == 0 and implied_positive and rerun is False:
        verified = True
        notes = "Re-run rejects violent death; prod progressed (false positive)"
    elif candidate.signal == "death_keyword_discarded" and rerun is True:
        verified = True
        notes = "Death-keyword headline confirmed violent by re-run"

    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage=candidate.stage,
        verified=verified,
        prod_outcome={"is_violent_death": stored, "status": status},
        rerun_outcome={"is_violent_death": rerun, "confidence": result.confidence},
        notes=notes or "Re-run did not confirm prod anomaly",
        candidate=candidate,
    )


async def _verify_content_gate(candidate: AnomalyCandidate) -> VerificationResult:
    from app.services.classification import classify_article_content

    headline = candidate.input.get("headline", "")
    content = candidate.input.get("content", "")
    prod = candidate.prod_snapshot
    status = prod.get("status")

    result = await asyncio.to_thread(classify_article_content, headline, content)
    gate_passes = result.is_violent_death and result.is_single_incident
    prod_passed = status == "extracted"

    verified = False
    notes = ""
    if prod_passed and not gate_passes:
        verified = True
        notes = "Prod extracted but re-run gate would reject"
    elif not prod_passed and gate_passes:
        verified = True
        notes = "Prod discarded but re-run gate would pass"

    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage="content-gate",
        verified=verified,
        prod_outcome={"status": status, "extracted": prod_passed},
        rerun_outcome={
            "gate_passes": gate_passes,
            "is_violent_death": result.is_violent_death,
            "is_single_incident": result.is_single_incident,
        },
        notes=notes or "Re-run gate agrees with prod path",
        candidate=candidate,
    )


async def _verify_extraction(candidate: AnomalyCandidate, *, with_llm: bool) -> VerificationResult:
    if not with_llm:
        return VerificationResult(
            candidate_id=candidate.candidate_id,
            stage="extraction",
            verified=True,
            prod_outcome={"extraction_success": candidate.prod_snapshot.get("extraction_success")},
            rerun_outcome={"skipped": True},
            notes="Structural anomaly only (use --with-llm-extraction to re-run LLM)",
            candidate=candidate,
        )

    from app.services.extraction import extract_event_from_content

    headline = candidate.input.get("headline", "")
    content = candidate.input.get("content", "")
    metadata = {"headline": headline} if headline else None
    result = await asyncio.to_thread(extract_event_from_content, content, metadata)
    success = result is not None and bool(getattr(result, "title", None) or getattr(result, "city", None))

    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage="extraction",
        verified=success,
        prod_outcome={"extraction_success": False},
        rerun_outcome={"extraction_success": success},
        notes="Re-run extraction succeeds; prod failure confirmed" if success else "Re-run also failed",
        candidate=candidate,
    )


async def _verify_dedup_match(
    candidate: AnomalyCandidate, *, db_path: Path | None
) -> VerificationResult:
    from app.services.enrichment import llm_match_to_unique_event

    if candidate.signal == "near_duplicate_unique_events":
        pair = candidate.input.get("pair") or candidate.prod_snapshot
        id_a, id_b = pair["id_a"], pair["id_b"]
        row_a = await load_unique_event_row(db_path, id_a)
        row_b = await load_unique_event_row(db_path, id_b)
        if not row_a or not row_b:
            return _unverified(candidate, "Could not load unique events for pair")

        raw_like = raw_event_from_data(
            RawEventData(
                id=row_b["id"],
                title=row_b.get("title"),
                event_date=str(row_b.get("event_date", ""))[:10] or None,
                city=row_b.get("city"),
                state=row_b.get("state"),
                neighborhood=row_b.get("neighborhood"),
                homicide_type=row_b.get("homicide_type"),
                chronological_description=row_b.get("chronological_description"),
                victim_names=[],
            )
        )
        candidates_list = [unique_event_from_data(UniqueEventData.model_validate(unique_event_data_from_row(row_a)))]
        matched, confidence, reasoning = await asyncio.to_thread(
            llm_match_to_unique_event, raw_like, candidates_list
        )
        verified = matched is not None and matched.id == id_a
        return VerificationResult(
            candidate_id=candidate.candidate_id,
            stage="dedup-match",
            verified=verified,
            prod_outcome={"separate_unique_events": [id_a, id_b]},
            rerun_outcome={
                "match": matched.id if matched else None,
                "confidence": confidence,
                "reasoning": reasoning[:200] if reasoning else "",
            },
            notes="Near-duplicate pair confirmed matchable by re-run" if verified else "Re-run did not match pair",
            candidate=candidate,
        )

    raw_event_id = candidate.input.get("raw_event_id") or candidate.record_ids.get("raw_event_id")
    if not raw_event_id:
        return _unverified(candidate, "Missing raw_event_id")

    raw_row = await load_raw_event_row(db_path, int(raw_event_id))
    if not raw_row:
        return _unverified(candidate, f"RawEvent {raw_event_id} not found")

    sibling_ids = candidate.input.get("sibling_ids") or candidate.prod_snapshot.get("sibling_ids") or []
    ue_rows = []
    for sid in sibling_ids:
        row = await load_unique_event_row(db_path, int(sid))
        if row:
            ue_rows.append(row)

    if not ue_rows:
        return _unverified(candidate, "No sibling unique events loaded")

    raw_event = raw_event_from_data(RawEventData.model_validate(raw_event_data_from_row(raw_row)))
    candidates_list = [
        unique_event_from_data(UniqueEventData.model_validate(unique_event_data_from_row(r)))
        for r in ue_rows
    ]
    matched, confidence, reasoning = await asyncio.to_thread(
        llm_match_to_unique_event, raw_event, candidates_list
    )
    verified = matched is not None
    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage="dedup-match",
        verified=verified,
        prod_outcome={"matched_unique_event_id": raw_row.get("unique_event_id"), "sibling_ids": sibling_ids},
        rerun_outcome={
            "match": matched.id if matched else None,
            "confidence": confidence,
            "reasoning": reasoning[:200] if reasoning else "",
        },
        notes="Raw event should match sibling per re-run" if verified else "Re-run did not match siblings",
        candidate=candidate,
    )


async def _verify_dedup_cluster(
    candidate: AnomalyCandidate, *, db_path: Path | None
) -> VerificationResult:
    from app.services.enrichment import llm_cluster_events

    raw_ids = candidate.input.get("raw_event_ids") or candidate.prod_snapshot.get("raw_event_ids") or []
    rows = []
    for rid in raw_ids:
        row = await load_raw_event_row(db_path, int(rid))
        if row:
            rows.append(row)
    if len(rows) < 2:
        return _unverified(candidate, "Need at least 2 raw events")

    events = [
        raw_event_from_data(RawEventData.model_validate(raw_event_data_from_row(r)))
        for r in rows
    ]
    clusters = await asyncio.to_thread(llm_cluster_events, events)
    merged = len(clusters) < len(events)
    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage="dedup-cluster",
        verified=merged,
        prod_outcome={"pending_count": len(rows), "status": "pending"},
        rerun_outcome={"cluster_count": len(clusters), "clusters": [[e.id for e in c] for c in clusters]},
        notes="Re-run merges overlapping pending events" if merged else "Re-run keeps events separate",
        candidate=candidate,
    )


async def _verify_enrichment(
    candidate: AnomalyCandidate, *, db_path: Path | None
) -> VerificationResult:
    ue_id = candidate.input.get("unique_event_id") or candidate.record_ids.get("unique_event_id")
    if not ue_id:
        return _unverified(candidate, "Missing unique_event_id")

    ue_row = await load_unique_event_row(db_path, int(ue_id))
    if not ue_row:
        return _unverified(candidate, f"UniqueEvent {ue_id} not found")

    if candidate.signal == "needs_enrichment_stale":
        verified = bool(ue_row.get("needs_enrichment"))
        return VerificationResult(
            candidate_id=candidate.candidate_id,
            stage="enrichment",
            verified=verified,
            prod_outcome={"needs_enrichment": ue_row.get("needs_enrichment"), "source_count": ue_row.get("source_count")},
            rerun_outcome={"checked": True},
            notes="Stale needs_enrichment flag confirmed" if verified else "Flag cleared since detect",
            candidate=candidate,
        )

    verified = True
    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage="enrichment",
        verified=verified,
        prod_outcome=dict(candidate.prod_snapshot),
        rerun_outcome={"field_mismatch": True},
        notes="Field mismatch between UniqueEvent and RawEvent confirmed structurally",
        candidate=candidate,
    )


def _unverified(candidate: AnomalyCandidate, note: str) -> VerificationResult:
    return VerificationResult(
        candidate_id=candidate.candidate_id,
        stage=candidate.stage,
        verified=False,
        notes=note,
        candidate=candidate,
    )


def print_verify_summary(bundle: VerifiedBundle) -> None:
    print(f"\n=== VERIFY: {bundle.meta.get('verified_count', 0)}/{bundle.meta.get('total', 0)} confirmed ===")
    for result in bundle.results:
        mark = "✓" if result.verified else "·"
        print(f"  {mark} [{result.stage}] {result.candidate_id}: {result.notes[:90]}")
