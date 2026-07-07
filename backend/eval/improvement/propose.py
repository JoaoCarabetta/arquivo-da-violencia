"""Convert verified anomalies into pending eval fixture cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.improvement.schemas import ProposedBundle, ProposedCase, VerifiedBundle, utc_now_iso
from eval.schemas import CaseMetadata


async def run_propose(*, verified_path: Path, output: Path | None) -> ProposedBundle:
    bundle = VerifiedBundle.model_validate(json.loads(verified_path.read_text()))
    cases: list[ProposedCase] = []

    for result in bundle.results:
        if not result.verified:
            continue
        case_dict, suggested = _to_fixture_case(result)
        cases.append(
            ProposedCase(
                stage=result.stage,
                case=case_dict,
                verification=result,
                suggested_expected=suggested,
            )
        )

    proposed = ProposedBundle(
        meta={
            "command": "propose",
            "run_at": utc_now_iso(),
            "source": str(verified_path),
            "total_verified": sum(1 for r in bundle.results if r.verified),
            "proposed_count": len(cases),
        },
        cases=cases,
    )

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(proposed.model_dump(mode="json"), ensure_ascii=False, indent=2))

    return proposed


def _to_fixture_case(result) -> tuple[dict[str, Any], dict[str, Any] | None]:
    candidate = result.candidate
    notes = f"{candidate.reason}. Verify: {result.notes}"
    meta = CaseMetadata(
        source_id=_int_or_none(candidate.record_ids.get("source_id")),
        notes=notes,
    )

    if result.stage == "classification":
        suggested = None
        if result.rerun_outcome.get("is_violent_death") is not None:
            suggested = {"is_violent_death": result.rerun_outcome["is_violent_death"]}
        case = {
            "id": candidate.candidate_id,
            "tags": [candidate.signal, "prod_anomaly"],
            "label_status": "pending",
            "input": {"headline": candidate.input.get("headline", "")},
            "expected": None,
            "metadata": meta.model_dump(mode="json"),
        }
        return case, suggested

    if result.stage == "content-gate":
        suggested = None
        if "is_violent_death" in result.rerun_outcome:
            suggested = {
                "is_violent_death": result.rerun_outcome.get("is_violent_death"),
                "is_single_incident": result.rerun_outcome.get("is_single_incident"),
            }
        case = {
            "id": candidate.candidate_id,
            "tags": [candidate.signal, "prod_anomaly"],
            "label_status": "pending",
            "input": {
                "headline": candidate.input.get("headline", ""),
                "content": candidate.input.get("content", ""),
            },
            "expected": None,
            "metadata": meta.model_dump(mode="json"),
        }
        return case, suggested

    if result.stage == "extraction":
        case = {
            "id": candidate.candidate_id,
            "tags": [candidate.signal, "prod_anomaly"],
            "label_status": "pending",
            "input": {
                "headline": candidate.input.get("headline", ""),
                "content": candidate.input.get("content", ""),
            },
            "expected": None,
            "metadata": meta.model_dump(mode="json"),
        }
        return case, None

    if result.stage == "dedup-match":
        suggested = {"match": True}
        if result.rerun_outcome.get("match"):
            suggested["unique_event_id"] = result.rerun_outcome["match"]
        case = {
            "id": candidate.candidate_id,
            "tags": [candidate.signal, "prod_anomaly"],
            "label_status": "pending",
            "input": candidate.input,
            "expected": None,
            "metadata": meta.model_dump(mode="json"),
        }
        return case, suggested

    if result.stage == "dedup-cluster":
        raw_ids = candidate.input.get("raw_event_ids") or []
        suggested = {"clusters": [list(range(1, len(raw_ids) + 1))]} if raw_ids else None
        case = {
            "id": candidate.candidate_id,
            "tags": [candidate.signal, "prod_anomaly"],
            "label_status": "pending",
            "input": candidate.input,
            "expected": None,
            "metadata": meta.model_dump(mode="json"),
        }
        return case, suggested

    if result.stage == "enrichment":
        case = {
            "id": candidate.candidate_id,
            "tags": [candidate.signal, "prod_anomaly"],
            "label_status": "pending",
            "input": candidate.input,
            "expected": None,
            "metadata": meta.model_dump(mode="json"),
        }
        return case, None

    case = {
        "id": candidate.candidate_id,
        "tags": [candidate.signal],
        "label_status": "pending",
        "input": candidate.input,
        "expected": None,
        "metadata": meta.model_dump(mode="json"),
    }
    return case, None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def print_propose_summary(bundle: ProposedBundle) -> None:
    print(f"\n=== PROPOSE: {bundle.meta.get('proposed_count', 0)} pending cases ===")
    print("  Awaiting human approval before merge into tests/fixtures/eval/")
    for item in bundle.cases:
        suggested = item.suggested_expected
        print(f"  - [{item.stage}] {item.case['id']}")
        if suggested:
            print(f"      suggested expected: {suggested}")
