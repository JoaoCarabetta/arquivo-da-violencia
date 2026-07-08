"""Human-readable review reports for eval improvement candidates."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from eval.improvement.schemas import (
    AnomalyCandidate,
    CandidateBundle,
    ProposedBundle,
    VerificationResult,
    VerifiedBundle,
)


class DbEnricher:
    """Load incident context from a SQLite snapshot."""

    def __init__(self, db_path: Path | None) -> None:
        self._conn: sqlite3.Connection | None = None
        if db_path and db_path.exists():
            self._conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def unique_event(self, event_id: int) -> dict[str, Any] | None:
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT id, title, city, state, event_date, victims_summary, source_count "
            "FROM unique_event WHERE id = ?",
            (event_id,),
        ).fetchone()
        return dict(row) if row else None

    def raw_event(self, raw_id: int) -> dict[str, Any] | None:
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT id, title, city, state, event_date, deduplication_status, unique_event_id "
            "FROM raw_event WHERE id = ?",
            (raw_id,),
        ).fetchone()
        return dict(row) if row else None

    def source(self, source_id: int) -> dict[str, Any] | None:
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT id, headline, status, is_violent_death FROM source_google_news WHERE id = ?",
            (source_id,),
        ).fetchone()
        return dict(row) if row else None


def _clip(text: str | None, n: int = 100) -> str:
    if not text:
        return "—"
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _one_line_summary(candidate: AnomalyCandidate, db: DbEnricher) -> str:
    stage = candidate.stage
    snap = candidate.prod_snapshot

    if stage == "dedup-match" and "id_a" in snap:
        a = db.unique_event(int(snap["id_a"])) or {}
        b = db.unique_event(int(snap["id_b"])) or {}
        city = a.get("city") or b.get("city") or "?"
        day = str(a.get("event_date") or b.get("event_date") or "")[:10]
        title = _clip(a.get("title") or b.get("title"), 55)
        return f"{city} {day} — {title}"

    if stage == "dedup-cluster":
        ids = candidate.input.get("raw_event_ids") or snap.get("raw_event_ids") or []
        if ids:
            first = db.raw_event(int(ids[0])) or {}
            city = first.get("city") or "?"
            day = str(first.get("event_date") or "")[:10]
            return f"{city} {day} — {len(ids)} pending raw events overlap"
        return candidate.reason[:80]

    if stage == "classification":
        return _clip(candidate.input.get("headline") or snap.get("headline"), 80)

    if stage == "content-gate":
        h = _clip(candidate.input.get("headline") or snap.get("headline"), 50)
        return f"{h} (content gate)"

    if stage == "extraction":
        return _clip(candidate.input.get("headline") or snap.get("title"), 80)

    if stage == "enrichment":
        ue_id = candidate.input.get("unique_event_id") or snap.get("unique_event_id")
        if ue_id:
            ue = db.unique_event(int(ue_id)) or {}
            return f"UE {ue_id} {_clip(ue.get('title'), 50)}"
        return candidate.reason[:80]

    return _clip(candidate.reason, 80)


def _status_label(verified: VerificationResult | None) -> str:
    if verified is None:
        return "detected"
    return "verified ✓" if verified.verified else "unverified ✗"


def _format_unique_event_block(db: DbEnricher, event_id: int, label: str) -> list[str]:
    row = db.unique_event(event_id)
    if not row:
        return [f"**{label}** (id={event_id}): not in snapshot"]
    lines = [
        f"**{label}** — UE `{row['id']}` | {str(row.get('event_date') or '')[:10]} | "
        f"{row.get('city') or '?'}, {row.get('state') or '?'}"
        f" | sources={row.get('source_count') or 0}",
        f"- Title: {_clip(row.get('title'), 120)}",
    ]
    if row.get("victims_summary"):
        lines.append(f"- Victims: {_clip(row['victims_summary'], 120)}")
    return lines


def _format_candidate_detail(
    index: int,
    candidate: AnomalyCandidate,
    verified: VerificationResult | None,
    suggested: dict[str, Any] | None,
    db: DbEnricher,
) -> str:
    status = _status_label(verified)
    lines = [
        f"### {index}. `{candidate.candidate_id}` — {status}",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Stage | `{candidate.stage}` |",
        f"| Signal | `{candidate.signal}` |",
        f"| Summary | {_one_line_summary(candidate, db)} |",
        "",
        f"**Why flagged:** {candidate.reason}",
        "",
    ]

    snap = candidate.prod_snapshot

    if candidate.stage == "dedup-match" and "id_a" in snap:
        lines.append("**Incidents in prod (still separate):**")
        lines.append("")
        lines.extend(_format_unique_event_block(db, int(snap["id_a"]), "Event A"))
        lines.append("")
        lines.extend(_format_unique_event_block(db, int(snap["id_b"]), "Event B"))
        if snap.get("similarity"):
            lines.append("")
            lines.append(
                f"Heuristic: `{snap.get('signal', '?')}` similarity={snap.get('similarity')}"
            )

    elif candidate.stage == "dedup-cluster":
        raw_ids = candidate.input.get("raw_event_ids") or snap.get("raw_event_ids") or []
        lines.append("**Pending raw events (should cluster?):**")
        lines.append("")
        for rid in raw_ids[:8]:
            row = db.raw_event(int(rid))
            if row:
                lines.append(
                    f"- Raw `{row['id']}` | {str(row.get('event_date') or '')[:10]} | "
                    f"{row.get('city') or '?'} | {_clip(row.get('title'), 70)}"
                )
            else:
                lines.append(f"- Raw `{rid}` (not in snapshot)")
        if len(raw_ids) > 8:
            lines.append(f"- … and {len(raw_ids) - 8} more")

    elif candidate.stage == "classification":
        headline = candidate.input.get("headline") or snap.get("headline") or "—"
        lines.append(f"**Headline:** {headline}")
        lines.append("")
        lines.append(
            f"**Prod:** status=`{snap.get('status')}` is_violent_death=`{snap.get('is_violent_death')}`"
        )

    elif candidate.stage == "content-gate":
        lines.append(f"**Headline:** {candidate.input.get('headline') or snap.get('headline') or '—'}")
        lines.append(f"**Prod status:** `{snap.get('status')}`")

    elif candidate.stage == "extraction":
        lines.append(f"**Headline:** {candidate.input.get('headline') or snap.get('title') or '—'}")
        lines.append(f"**Prod extraction_success:** `{snap.get('extraction_success')}`")

    elif candidate.stage == "enrichment":
        ue_id = candidate.input.get("unique_event_id") or snap.get("unique_event_id")
        if ue_id:
            lines.extend(_format_unique_event_block(db, int(ue_id), "Unique event"))

    if verified:
        lines.append("")
        lines.append("**Verification (re-run):**")
        lines.append(f"- Notes: {verified.notes}")
        if verified.rerun_outcome:
            lines.append(f"- Re-run outcome: `{json.dumps(verified.rerun_outcome, ensure_ascii=False)}`")

    if suggested:
        lines.append("")
        lines.append(
            f"**Suggested eval label:** `{json.dumps(suggested, ensure_ascii=False)}`"
        )

    lines.extend(
        [
            "",
            "**Your decision:** ☐ Approve &nbsp; ☐ Reject &nbsp; ☐ Edit label",
            "",
            "---",
            "",
        ]
    )
    return "\n".join(lines)


def build_review_markdown(
    *,
    candidates: list[AnomalyCandidate],
    verified_by_id: dict[str, VerificationResult] | None = None,
    suggested_by_id: dict[str, dict[str, Any] | None] | None = None,
    db_path: Path | None = None,
    title: str = "Eval improvement review",
    meta: dict[str, Any] | None = None,
) -> str:
    verified_by_id = verified_by_id or {}
    suggested_by_id = suggested_by_id or {}
    db = DbEnricher(db_path)

    by_stage: dict[str, list[AnomalyCandidate]] = {}
    for c in candidates:
        by_stage.setdefault(c.stage, []).append(c)

    lines = [
        f"# {title}",
        "",
    ]
    if meta:
        for key in ("date_from", "date_to", "db", "run_at", "source"):
            if meta.get(key):
                lines.append(f"- **{key}:** `{meta[key]}`")
        if meta.get("by_stage"):
            counts = ", ".join(f"{k}: {v}" for k, v in sorted(meta["by_stage"].items()))
            lines.append(f"- **Counts:** {counts}")
        lines.append("")

    lines.extend(
        [
            "## Quick list",
            "",
            "| # | Stage | ID | Status | Summary |",
            "|---|-------|----|--------|---------|",
        ]
    )

    for i, c in enumerate(candidates, start=1):
        v = verified_by_id.get(c.candidate_id)
        status = _status_label(v)
        summary = _one_line_summary(c, db).replace("|", "\\|")
        lines.append(
            f"| {i} | `{c.stage}` | `{c.candidate_id}` | {status} | {summary} |"
        )

    lines.extend(["", "## Details", ""])

    for i, c in enumerate(candidates, start=1):
        lines.append(
            _format_candidate_detail(
                i,
                c,
                verified_by_id.get(c.candidate_id),
                suggested_by_id.get(c.candidate_id),
                db,
            )
        )

    lines.extend(
        [
            "## How to respond",
            "",
            "Reply with approved case IDs, e.g.:",
            "",
            "```",
            "approve: prod-dedup_match-9722-9723, prod-dedup_match-9732-9743",
            "reject: prod-dedup_match-9722-9730",
            "```",
            "",
            "Only approved cases will be merged into `backend/tests/fixtures/eval/`.",
            "",
        ]
    )

    db.close()
    return "\n".join(lines)


def review_from_candidates(
    path: Path,
    *,
    verified_path: Path | None = None,
    proposed_path: Path | None = None,
    db_path: Path | None = None,
) -> str:
    bundle = CandidateBundle.model_validate(json.loads(path.read_text()))
    candidates = bundle.candidates

    verified_by_id: dict[str, VerificationResult] = {}
    suggested_by_id: dict[str, dict[str, Any] | None] = {}

    if verified_path and verified_path.exists():
        vb = VerifiedBundle.model_validate(json.loads(verified_path.read_text()))
        for r in vb.results:
            verified_by_id[r.candidate_id] = r

    if proposed_path and proposed_path.exists():
        pb = ProposedBundle.model_validate(json.loads(proposed_path.read_text()))
        for item in pb.cases:
            suggested_by_id[item.case["id"]] = item.suggested_expected
            verified_by_id[item.case["id"]] = item.verification
        # keep candidate list from proposed if candidates file missing entries
        if not candidates:
            candidates = [item.verification.candidate for item in pb.cases]

    title = "Eval improvement review"
    if bundle.meta.get("date_from") and bundle.meta.get("date_to"):
        title = f"Eval review — {bundle.meta['date_from']} to {bundle.meta['date_to']}"

    return build_review_markdown(
        candidates=candidates,
        verified_by_id=verified_by_id,
        suggested_by_id=suggested_by_id,
        db_path=db_path,
        title=title,
        meta=bundle.meta,
    )


def review_from_verified(path: Path, *, db_path: Path | None = None) -> str:
    vb = VerifiedBundle.model_validate(json.loads(path.read_text()))
    candidates = [r.candidate for r in vb.results]
    verified_by_id = {r.candidate_id: r for r in vb.results}
    return build_review_markdown(
        candidates=candidates,
        verified_by_id=verified_by_id,
        db_path=db_path,
        title="Eval improvement review (verified)",
        meta=vb.meta,
    )


def review_from_proposed(path: Path, *, db_path: Path | None = None) -> str:
    pb = ProposedBundle.model_validate(json.loads(path.read_text()))
    candidates = [item.verification.candidate for item in pb.cases]
    verified_by_id = {item.case["id"]: item.verification for item in pb.cases}
    suggested_by_id = {item.case["id"]: item.suggested_expected for item in pb.cases}
    return build_review_markdown(
        candidates=candidates,
        verified_by_id=verified_by_id,
        suggested_by_id=suggested_by_id,
        db_path=db_path,
        title="Eval improvement review (awaiting approval)",
        meta=pb.meta,
    )


def default_review_path(output_json: Path) -> Path:
    stem = output_json.stem
    if stem.endswith("-review"):
        return output_json
    return output_json.with_name(f"{stem}-review.md")


def write_review(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def print_review_pointer(path: Path, count: int) -> None:
    print(f"\n📋 Review report ({count} cases): {path}")
    print("   Open this file for the full table and per-case approve/reject checklist.")


def emit_review_for_output(
    output_json: Path,
    *,
    db_path: Path | None = None,
    verified_path: Path | None = None,
    proposed_path: Path | None = None,
    review_path: Path | None = None,
) -> tuple[Path, int]:
    """Write a Markdown review alongside detect/verify/propose JSON output."""
    data = json.loads(output_json.read_text())

    if data.get("cases") and data["cases"] and "verification" in data["cases"][0]:
        md = review_from_proposed(output_json, db_path=db_path)
        count = len(data["cases"])
    elif "results" in data:
        md = review_from_verified(output_json, db_path=db_path)
        count = len(data["results"])
    elif "candidates" in data:
        md = review_from_candidates(
            output_json,
            verified_path=verified_path,
            proposed_path=proposed_path,
            db_path=db_path,
        )
        count = len(data["candidates"])
    else:
        raise ValueError(f"Unrecognized improvement output format: {output_json}")

    out = review_path or default_review_path(output_json)
    write_review(out, md)
    return out, count
