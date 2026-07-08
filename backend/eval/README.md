# Pipeline eval harness

Benchmarks for every LLM call site in the pipeline. Each stage has labeled
fixtures under `backend/tests/fixtures/eval/`, run reports land in
`backend/eval/results/`, and prompt/model experiments are described by variant
YAMLs under `backend/eval/variants/`.

## Stages

| CLI stage | Production call site | Model env var | Fixtures |
|---|---|---|---|
| `classification` | `classify_headline` (`app/services/classification.py`) | `SELECTION_MODEL` | `classification_seed.json`, `classification_hard.json` |
| `content-gate` | `classify_article_content` (same file) | `CONTENT_GATE_MODEL` | `content_gate_seed.json`, `content_gate_hard.json` |
| `extraction` | `extract_event_from_content` (`app/services/extraction.py`) | `EXTRACTION_MODEL` | `extraction_seed.json`, `extraction_hard.json` |
| `dedup-match` | `llm_match_to_unique_event` (`app/services/enrichment.py`) | `DEDUP_MODEL` | `dedup_match_seed.json` |
| `dedup-cluster` | `llm_cluster_events` (same file) | `DEDUP_MODEL` | `dedup_cluster_seed.json` |
| `enrichment` | `synthesize_unique_event` (same file) | `ENRICHMENT_MODEL` | `enrichment_seed.json` |

Every stage supports `validate`, `build`, `run`, and `report`;
`classification`, `content-gate`, and `extraction` also support
`generate-hard` (adversarial case generation, costs tokens), and
`classification` supports `compare`.

## Running evals (Docker)

LLM-backed runs need `OPENROUTER_API_KEY` (from `.env`) and are run inside the
API image per repo convention:

```bash
docker run --rm --env-file .env \
  -v "$PWD/backend/eval:/app/eval" \
  -v "$PWD/backend/tests:/app/tests" \
  -v "$PWD/backend/app:/app/app:ro" \
  arquivo-da-violencia-api \
  python -m eval <stage> run --fixture tests/fixtures/eval/<fixture>.json \
    --output eval/results/<name>.json
```

Useful flags on `run`: `--variant <name>` (see below), `--limit N`,
`--ids id1,id2`, `--concurrency N`, `--no-llm` (dry run).

Validation and reporting don't need an API key:

```bash
python -m eval dedup-cluster validate
python -m eval extraction report --run eval/results/extraction-hard-baseline.json
```

## Variants

A variant YAML in `backend/eval/variants/` overrides the model and/or system
prompt without touching production code:

```yaml
# variants/my-experiment.yaml
# Models are OpenRouter slugs: "<vendor>/<model>".
model: google/gemini-2.5-flash-lite            # generic: content-gate / dedup / enrichment stages
selection_model: google/gemini-2.5-flash-lite  # classification stage
extraction_model: google/gemini-2.5-flash-lite # extraction stage
# per-stage keys also work: content_gate_model, dedup_model, enrichment_model
system_prompt_file: my_prompt.txt              # optional, relative to variants/
```

Run with `--variant my-experiment`. `--variant baseline` (default) uses the
production prompt and model. Promote a winning prompt by copying it into the
corresponding `*_SYSTEM_PROMPT` constant in `app/services/`.

## Building fixtures

Fixtures are bootstrapped from a prod DB copy (e.g. `data/violence-copy.db`)
and then hand-checked — bootstrap labels inherit prod-pipeline mistakes
(notably duplicate unique events), so review before trusting scores:

```bash
python -m eval dedup-match build --db data/violence-copy.db --n 30
python -m eval content-gate build --db data/violence-copy.db --n 15 --with-labels
```

`--merge-into <existing.json>` appends only new case IDs instead of
overwriting.

## Model benchmark (Jul 2026, via OpenRouter)

All LLM traffic goes through OpenRouter (`OPENROUTER_API_KEY`); clients use
instructor's `openrouter/` provider in JSON mode (tool-calling mode hangs
intermittently through OpenRouter). Pass rates per stage/model (reports in
`results/bench-*` and `results/final-*`). Prices are USD per 1M input/output
tokens.

| Stage (fixture) | gemini-2.5-flash ($0.30/$2.50) | gemini-2.5-flash-lite ($0.10/$0.40) | gemini-3.1-flash-lite ($0.25/$1.50) | deepseek-v4-flash ($0.09/$0.18) | qwen3.5-flash ($0.065/$0.26) | gpt-oss-120b ($0.03/$0.15) | Pick |
|---|---|---|---|---|---|---|---|
| classification (seed/hard) | – | 100% / 93.3% | – | 100% / 100% | 100% / 100% | **100% / 100%** | gpt-oss-120b |
| content-gate (seed/hard) | – | **93.3% / 100%** | – | 86.7% / 100% | 80% / 100% | 86.7% / 100% | 2.5-flash-lite |
| extraction (seed/hard, mean) | 92.9% / 95.0% | – | – | **92.9% / 95.8%** | 90.5% / 98.3% | 88.1% / 95.8% | deepseek-v4-flash |
| dedup-match | – | – | **96.6–100%** | 96.6% | 96.6% | 93.1% | 3.1-flash-lite |
| dedup-cluster (exact/F1) | – | – | **100% / 100%** | 92% / 98.0% | 92% / 97.6% | 76% / 92.7% | 3.1-flash-lite |
| enrichment (mean) | – | 100% | – | **100%** | 100% | 88% | deepseek-v4-flash |

The picks are wired as defaults in `app/config.py` (`EXTRACTION_MODEL`,
`SELECTION_MODEL`, `CONTENT_GATE_MODEL`, `DEDUP_MODEL`, `ENRICHMENT_MODEL`).
Rationale:

- **Headline classification → gpt-oss-120b**: perfect on both fixtures and the
  cheapest model tested (~3x cheaper than 2.5-flash-lite, which drops to
  93.3% on the hard set through OpenRouter).
- **Content gate → gemini-2.5-flash-lite** (unchanged): every cheaper model
  loses 1–2 seed cases (legal-process articles); the gate protects extraction
  spend so accuracy wins.
- **Extraction → deepseek-v4-flash**: matches gemini-2.5-flash on seed and
  beats it on hard, at ~1/10 the blended price (the biggest single cost win —
  extraction sees the longest prompts in the pipeline).
- **Dedup → gemini-3.1-flash-lite** (unchanged): only model at 100% exact
  partition on clustering; wrong merges corrupt unique events, so no swap.
- **Enrichment → deepseek-v4-flash**: ties 2.5-flash-lite at 100% and is
  cheaper on both input and output.

The only remaining dedup-match miss (`dm-dup-8255`) is a genuinely ambiguous
pair (same first name, different surnames reported by different outlets) that
every model resolves the same way.

## Scoring per stage

- **classification / content-gate** — accuracy, precision, recall, F1 on the
  gate decision (`is_violent_death` AND `is_single_incident` for the gate).
- **extraction** — per-field scores (date, city, state, victim info, etc.)
  aggregated into a mean score per case; case passes above threshold.
- **dedup-match** — accuracy of the match decision and matched ID (positives
  must pick the right unique event, negatives must return no-match).
- **dedup-cluster** — exact partition match rate plus pairwise
  precision/recall/F1 over same-cluster pairs.
- **enrichment** — field-level accuracy of the synthesized unique event
  (event_date, city, state, victim_count).

## Eval improvement loop

Interactive workflow (Cursor skill: `.cursor/skills/eval-improvement-loop/`) to
find production pipeline mistakes, verify them, propose eval cases for human
approval, and iterate until the full suite passes.

```bash
# 1. Detect anomalies (read-only SQL; use staging DATABASE_URL or --db snapshot)
python -m eval improvement detect --only-stage all --limit 20 \
  --output eval/results/proposed/candidates.json

# 2. Verify with production re-runs (LLM cost)
python -m eval improvement verify \
  --candidates eval/results/proposed/candidates.json \
  --db eval/results/proposed/prod-snapshot.db \
  --output eval/results/proposed/verified.json

# 3. Propose pending fixture cases (human must approve before merge)
python -m eval improvement propose \
  --verified eval/results/proposed/verified.json \
  --db eval/results/proposed/prod-snapshot.db \
  --output eval/results/proposed/proposed.json

Each step with `--output` also writes a `*-review.md` with **fix recommendation
clusters** (root cause + algorithm change) and a candidate appendix. Show the fix
table to the user and wait for `approve-fix:` before changing code.

# 4. Full 100% gate across all configured fixtures
python -m eval improvement run-all --output eval/results/run-all.json

# 5. Compare any two run reports for regressions
python -m eval improvement compare-reports \
  --baseline eval/results/baseline.json \
  --candidate eval/results/candidate.json
```

Or: `bash .cursor/skills/eval-improvement-loop/scripts/run-all-eval.sh`

See the skill's `reference.md` for Docker commands and DB snapshot steps.
