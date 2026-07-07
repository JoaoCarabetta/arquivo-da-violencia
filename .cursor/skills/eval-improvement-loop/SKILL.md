---
name: eval-improvement-loop
description: >-
  Scans production/staging pipeline data for mistakes, verifies them with
  re-runs, proposes eval cases for human approval, then iterates prompt/code
  fixes against the full 6-stage eval suite until 100% pass. Use when improving
  pipeline quality, bootstrapping eval cases from prod anomalies, or chasing
  eval regressions across classification, content-gate, extraction, dedup, and
  enrichment.
---

# Eval Improvement Loop

Interactive workflow to turn **production mistakes** into **labeled eval cases**
and drive the pipeline to **100% eval pass** on all fixtures.

## Progress checklist

Copy and update as you go:

```
Eval improvement loop
- [ ] Phase 0: DB access confirmed (staging preferred)
- [ ] Phase 1: detect — candidates written to eval/results/proposed/
- [ ] Phase 2: verify — LLM re-runs confirm real anomalies
- [ ] Phase 3: propose — pending cases presented; HUMAN APPROVAL received
- [ ] Phase 4: merge approved cases into tests/fixtures/eval/
- [ ] Phase 5: run-all baseline
- [ ] Phase 6: fix loop until 100% (max 5 iterations)
- [ ] Phase 7: promote winning prompts/variants to production code
```

## Phase 0 — Setup

1. Prefer **staging** DB over production. See [reference.md](reference.md).
2. Confirm `OPENROUTER_API_KEY` in `.env` for verify/run-all LLM steps.
3. Use Docker per repo convention (see [reference.md](reference.md)).

## Phase 1 — Detect (no LLM cost)

```bash
python -m eval improvement detect --only-stage all --limit 20 --dry-run
python -m eval improvement detect --only-stage all --limit 20 --output eval/results/proposed/candidates-<ts>.json
```

Optional offline snapshot:

```bash
python -m eval improvement detect --db data/violence-copy.db --only-stage all --limit 20
```

Review the candidate count per stage. Abort if DB is unreachable.

## Phase 2 — Verify (LLM cost)

```bash
python -m eval improvement verify \
  --candidates eval/results/proposed/candidates-<ts>.json \
  --output eval/results/proposed/verified-<ts>.json
```

Add `--with-llm-extraction` only when extraction candidates need confirmation
(extraction verify is expensive).

## Phase 3 — Propose + human gate (mandatory)

```bash
python -m eval improvement propose \
  --verified eval/results/proposed/verified-<ts>.json \
  --output eval/results/proposed/proposed-<ts>.json
```

Present the user a table per case:

| id | stage | prod outcome | re-run outcome | signal | suggested expected |
|----|-------|--------------|----------------|--------|-------------------|

**STOP and wait for explicit approval** before merging into fixtures.

Rules:

- Never set `label_status: labeled` without user confirmation.
- Never merge into `backend/tests/fixtures/eval/` without approval.
- For ambiguous cases (e.g. `dm-dup-8255`), ask whether to fix label, add
  exception, or accept documented miss.

## Phase 4 — Merge approved cases

After approval:

1. Set `expected` and `label_status: labeled` on approved cases.
2. Merge into the appropriate fixture under `backend/tests/fixtures/eval/`.
3. Run `python -m eval <stage> validate --fixture <path>`.

Use `--merge-into` patterns from existing `build` commands when appending.

## Phase 5 — Full eval gate

```bash
bash .cursor/skills/eval-improvement-loop/scripts/run-all-eval.sh
# or:
python -m eval improvement run-all --output eval/results/run-all-<ts>.json
```

100% means every **labeled** case in every configured fixture passes
(`all_passed: true` in the summary).

## Phase 6 — Fix loop (max 5 iterations)

When `run-all` fails:

1. Triage failures from per-stage reports in `eval/results/`.
2. Classify: bad label vs prompt vs code heuristic.
3. Experiment with `backend/eval/variants/loop-<ts>.yaml` — run affected stage only.
4. Guard regressions:

   ```bash
   python -m eval classification compare --baseline <old> --candidate <new>
   python -m eval improvement compare-reports --baseline <old> --candidate <new>
   ```

5. Promote winning prompt to `app/services/*_SYSTEM_PROMPT` or config model.
6. Re-run `run-all`. Repeat until `all_passed: true` or max iterations.

Optional dynamic polling while fixing:

```text
/loop improve eval until run-all passes
```

## Abort conditions

Stop and ask the user when:

- DB unreachable or empty candidate set after detect
- Token budget exceeded (verify/run-all cost)
- Same case fails after 2 fix attempts — likely bad label or genuinely ambiguous
- Max iterations (5) reached without 100%
- Known ambiguous case persists (`dm-dup-8255` and similar)

## Files and outputs

| Artifact | Path |
|----------|------|
| Candidates | `backend/eval/results/proposed/candidates-*.json` |
| Verified | `backend/eval/results/proposed/verified-*.json` |
| Proposals | `backend/eval/results/proposed/proposed-*.json` |
| Run-all summary | `backend/eval/results/run-all-*.json` |
| Fixtures (after approval) | `backend/tests/fixtures/eval/*.json` |

See [reference.md](reference.md) for Docker commands and DB snapshot steps.
