---
name: eval-improvement-loop
description: >-
  Scans production/staging pipeline data for mistakes, builds a diagnosis report
  (root causes, scored solutions, eval recommendations), verifies with re-runs,
  and iterates prompt/code fixes against the full 6-stage eval suite until 100%
  pass. Use when improving pipeline quality, bootstrapping eval cases from prod
  anomalies, or chasing eval regressions across classification, content-gate,
  extraction, dedup, and enrichment.
---

# Eval Improvement Loop

Interactive workflow: **prod mistakes → diagnosis report → human `approve-fix:` →
implement elected solution + eval cases → 100% eval pass**.

## Progress checklist

```
Eval improvement loop
- [ ] Phase 0: DB access confirmed (staging preferred)
- [ ] Phase 1: detect — candidates + *-review.md written
- [ ] Phase 2: verify — LLM re-runs (optional but refines root-cause likelihood)
- [ ] Phase 3: diagnosis presented — HUMAN `approve-fix:` received
- [ ] Phase 4: ops heal (if needed) + implement elected code/prompt changes
- [ ] Phase 5: add eval cases where report says required/recommended
- [ ] Phase 6: run-all baseline
- [ ] Phase 7: fix loop until 100% (max 5 iterations)
- [ ] Phase 8: promote winning prompts/variants to production code
```

## Phase 0 — Setup

1. Prefer **staging** DB over production. See [reference.md](reference.md).
2. Confirm `OPENROUTER_API_KEY` in `.env` for verify/run-all LLM steps.
3. Use Docker per repo convention (see [reference.md](reference.md)).
4. For rich diagnosis examples, use a SQLite snapshot with `--db` (see reference).

## Phase 1 — Detect (no LLM cost)

```bash
python -m eval improvement detect --only-stage all --limit 20 --dry-run
python -m eval improvement detect --only-stage all --limit 20 \
  --output eval/results/proposed/candidates-<ts>.json \
  --db eval/results/proposed/prod-snapshot.db
```

When `--output` is set, a **`*-review.md`** diagnosis report is auto-written.
**Always pass `--db`** when you have a snapshot so the report includes real prod
examples (titles, victims, field mismatches).

Optional: pull snapshot from public API:

```bash
python -m eval improvement pull-snapshot \
  --api-base-url https://arquivodaviolencia.com.br \
  --date-from 2026-07-03 --date-to 2026-07-07 \
  --output eval/results/proposed/prod-snapshot.db
```

Abort if DB unreachable or zero candidates.

## Phase 2 — Verify (LLM cost, optional)

```bash
python -m eval improvement verify \
  --candidates eval/results/proposed/candidates-<ts>.json \
  --db eval/results/proposed/prod-snapshot.db \
  --output eval/results/proposed/verified-<ts>.json
```

Verify refines the diagnosis:
- Confirms/rejects root-cause hypotheses (e.g. LLM would match → stale prod state)
- Adjusts solution scores (boosts ops merge when re-run confirms match)

Add `--with-llm-extraction` only for extraction candidates (expensive).

## Phase 3 — Diagnosis + human gate (mandatory)

Regenerate the full report after verify/propose:

```bash
python -m eval improvement review \
  --candidates eval/results/proposed/candidates-<ts>.json \
  --verified eval/results/proposed/verified-<ts>.json \
  --db eval/results/proposed/prod-snapshot.db
```

Optional propose step (eval fixture drafts — secondary to fix approval):

```bash
python -m eval improvement propose \
  --verified eval/results/proposed/verified-<ts>.json \
  --db eval/results/proposed/prod-snapshot.db \
  --output eval/results/proposed/proposed-<ts>.json
```

### What the diagnosis report contains

Each `*-review.md` is clustered by **problem → solution** (not by city/incident).
For each fix cluster the report includes:

| Section | Purpose |
|---------|---------|
| **Fix recommendations** table | Summary: Problem, elected solution, score, affected, Eval? |
| **Possible root causes** | ≥3 hypotheses ranked by likelihood + how to confirm |
| **Solution options** | ≥3 alternatives scored 0–10 on 5 dimensions; **elected** winner |
| **What will be affected** | Incidents, UE IDs, raw event IDs, merge survivors |
| **Real examples** | Prod titles/victims/mismatches justifying the diagnosis |
| **Eval case needed?** | Yes/No, priority, fixture path, suggested cases + why |
| **Candidate appendix** | Traceability only — not the primary approval surface |

### Scoring metric (solution election)

Weighted score elects the best solution:

| Dimension | Weight | 0–10 meaning |
|-----------|--------|--------------|
| effectiveness | 35% | Fixes existing prod damage |
| permanence | 25% | Prevents recurrence |
| effort_inverse | 15% | 10 = low effort |
| risk_inverse | 15% | 10 = low regression risk |
| eval_signal | 10% | 10 = CI can catch regressions |

Implementation: `backend/eval/improvement/analysis.py`

### Present to the user (required)

1. Paste the **Fix recommendations** summary table.
2. For each fix the user cares about, quote:
   - Root cause hypotheses (top 2)
   - Solution score table + elected winner + pros/cons
   - **Real examples** (prod titles/victims)
   - **Eval case needed?** block (Yes/No and why)
3. **STOP and wait for `approve-fix:` / `reject-fix:` / `defer-fix:`**.

Example summary table:

| # | Fix ID | Problem | Elected solution | Score | Affected | Eval? |
|---|--------|---------|------------------|-------|----------|-------|
| 1 | `fix-dedup-match-victim-name` | Duplicate UEs not merged | Code: post-dedup near-dup scan | 8.38 | 3 incidents · 20 UEs | Yes |

Example approval:

```text
approve-fix: fix-dedup-match-victim-name, fix-dedup-cluster-pending-overlap-cluster
defer-fix: fix-enrichment-field-mismatch
note: run ops heal first (merge_near_duplicate + process_pending_deduplication) before code deploy
```

Separate eval-case approval (after fix decided):

```text
approve: prod-dedup_match-9722-9723, prod-dedup_match-9745-9757
```

Rules:

- User approves **fix clusters** (`approve-fix:`), not individual candidate IDs.
- Never implement code/prompt changes without `approve-fix:`.
- Never set `label_status: labeled` without user confirmation.
- When elected solution is **code** but **ops** ranks #2, recommend ops heal first
  to fix prod data, then deploy code to prevent recurrence.
- If **Eval? = Yes (required)**, add suggested cases before merging code changes.

## Phase 4 — Implement approved fixes

After `approve-fix:`:

1. **Ops heal** (if applicable): run maintenance merge, batch dedup, re-enrich.
2. **Code/prompt** changes per elected solution targets in the report.
3. **Eval cases**: add labeled cases from the report's "Suggested cases to label"
   into the fixture path shown in "Eval case needed?".
4. Validate fixtures: `python -m eval <stage> validate --fixture <path>`.

## Phase 5 — Full eval gate

```bash
bash .cursor/skills/eval-improvement-loop/scripts/run-all-eval.sh
# or:
python -m eval improvement run-all --output eval/results/run-all-<ts>.json
```

100% = `all_passed: true` on all configured fixtures.

## Phase 6 — Fix loop (max 5 iterations)

When `run-all` fails:

1. Triage failures from per-stage reports.
2. Classify: bad label vs prompt vs code heuristic.
3. Experiment with `backend/eval/variants/loop-<ts>.yaml`.
4. Compare regressions:

   ```bash
   python -m eval classification compare --baseline <old> --candidate <new>
   python -m eval improvement compare-reports --baseline <old> --candidate <new>
   ```

5. Promote winning prompt/config to production services.
6. Re-run `run-all`.

## Abort conditions

Stop and ask the user when:

- DB unreachable or empty candidate set after detect
- Token budget exceeded (verify/run-all cost)
- Same case fails after 2 fix attempts
- Max iterations (5) without 100%
- Eval recommendation is **required** but user rejects adding cases

## Files and outputs

| Artifact | Path |
|----------|------|
| Candidates | `backend/eval/results/proposed/candidates-*.json` |
| Verified | `backend/eval/results/proposed/verified-*.json` |
| Proposals | `backend/eval/results/proposed/proposed-*.json` |
| **Diagnosis report (show user)** | `backend/eval/results/proposed/*-review.md` |
| Run-all summary | `backend/eval/results/run-all-*.json` |
| Fixtures (after approval) | `backend/tests/fixtures/eval/*.json` |

Backend modules:

| Module | Role |
|--------|------|
| `eval/improvement/detect.py` | Find prod anomalies |
| `eval/improvement/diagnose.py` | Cluster by problem/solution |
| `eval/improvement/analysis.py` | Root causes, scored solutions, eval rec |
| `eval/improvement/examples.py` | Real prod examples from snapshot |
| `eval/improvement/review.py` | Markdown report generator |

See [reference.md](reference.md) for Docker commands and DB snapshot steps.
