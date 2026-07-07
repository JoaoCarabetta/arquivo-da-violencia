"""Detect production pipeline anomalies for eval case bootstrapping."""

from __future__ import annotations

import json
from pathlib import Path

from eval.improvement.detectors import detect_anomalies
from eval.improvement.schemas import ALL_STAGES, CandidateBundle, StageName, utc_now_iso


def parse_stages(stage_arg: str) -> list[StageName]:
    if stage_arg == "all":
        return list(ALL_STAGES)
    stage = stage_arg.replace("_", "-")
    if stage not in ALL_STAGES:
        raise SystemExit(f"Unknown stage: {stage_arg}. Choose from: all, {', '.join(ALL_STAGES)}")
    return [stage]  # type: ignore[list-item]


async def run_detect(
    *,
    db_path: Path | None,
    stages: list[StageName],
    limit: int,
    output: Path | None,
    dry_run: bool,
) -> CandidateBundle:
    candidates = await detect_anomalies(db_path=db_path, stages=stages, limit=limit)

    bundle = CandidateBundle(
        meta={
            "command": "detect",
            "run_at": utc_now_iso(),
            "db": str(db_path) if db_path else "DATABASE_URL",
            "stages": stages,
            "limit_per_stage": limit,
            "dry_run": dry_run,
            "total": len(candidates),
            "by_stage": _count_by_stage(candidates),
        },
        candidates=candidates,
    )

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2))

    return bundle


def print_detect_summary(bundle: CandidateBundle) -> None:
    print(f"\n=== DETECT: {bundle.meta.get('total', 0)} candidates ===")
    print(f"  db: {bundle.meta.get('db')}")
    print(f"  stages: {', '.join(bundle.meta.get('stages', []))}")
    by_stage = bundle.meta.get("by_stage", {})
    for stage, count in sorted(by_stage.items()):
        print(f"  {stage}: {count}")
    if bundle.candidates:
        print("\n  Sample:")
        for c in bundle.candidates[:5]:
            print(f"    - [{c.stage}] {c.candidate_id}: {c.signal} — {c.reason[:80]}")


def _count_by_stage(candidates) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in candidates:
        counts[c.stage] = counts.get(c.stage, 0) + 1
    return counts
