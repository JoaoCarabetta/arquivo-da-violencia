# Eval Improvement Loop — Reference

## Docker commands

From repo root with dev stack running:

```bash
# Detect (read-only, no LLM)
docker compose -f docker-compose.dev.yml exec api \
  python -m eval improvement detect --only-stage all --limit 10 --dry-run

docker compose -f docker-compose.dev.yml exec api \
  python -m eval improvement detect --only-stage all --limit 10 \
  --output eval/results/proposed/candidates.json

# Verify (LLM)
docker compose -f docker-compose.dev.yml exec api \
  python -m eval improvement verify \
  --candidates eval/results/proposed/candidates.json \
  --output eval/results/proposed/verified.json

# Propose pending cases
docker compose -f docker-compose.dev.yml exec api \
  python -m eval improvement propose \
  --verified eval/results/proposed/verified.json \
  --output eval/results/proposed/proposed.json

# Full eval gate
docker compose -f docker-compose.dev.yml exec api \
  python -m eval improvement run-all --output eval/results/run-all.json
```

One-off API image (matches eval README):

```bash
docker run --rm --env-file .env \
  -v "$PWD/backend/eval:/app/eval" \
  -v "$PWD/backend/tests:/app/tests" \
  -v "$PWD/backend/app:/app/app:ro" \
  arquivo-da-violencia-api \
  python -m eval improvement run-all
```

## Database access

**Staging first** (safer than prod):

| Environment | API | Notes |
|-------------|-----|-------|
| Staging | https://staging.arquivodaviolencia.com.br | Port 8001 on VPS |
| Production | https://arquivodaviolencia.com.br | Port 8000 on VPS |

Detect uses `DATABASE_URL` from the container env when `--db` is omitted.

**Offline SQLite snapshot** (matches existing `build` scripts):

```bash
# On prod/staging VPS
sqlite3 backend/app/instance/violence.db ".backup '/tmp/violence-copy.db'"
# scp to local data/violence-copy.db

python -m eval improvement detect --db data/violence-copy.db --only-stage all --limit 20
```

For Postgres staging/prod, `detect` uses async SQLAlchemy read queries only — no writes.

## Fixture targets (after human approval)

| Stage | Primary fixtures |
|-------|------------------|
| classification | `classification_seed.json`, `classification_hard.json` |
| content-gate | `content_gate_hard.json` |
| extraction | `extraction_hard.json` |
| dedup-match | `dedup_match_hard.json` |
| dedup-cluster | `dedup_cluster_seed.json` (create if missing) |
| enrichment | `enrichment_seed.json` (create if missing) |

Validate after merge:

```bash
python -m eval <stage> validate --fixture tests/fixtures/eval/<file>.json
```

## Variant experiments

```bash
cp backend/eval/variants/proposed.example.yaml backend/eval/variants/loop-1.yaml
python -m eval classification run --variant loop-1 --fixture tests/fixtures/eval/classification_hard.json
python -m eval classification compare --baseline eval/results/baseline.json --candidate eval/results/loop-1.json
```

Promote winning prompts to `app/services/classification.py`, `extraction.py`,
`enrichment.py`, etc.

## Cost control

| Step | Cost |
|------|------|
| detect --dry-run | Free (SQL only) |
| detect | Free (SQL only) |
| verify (except extraction) | LLM per candidate |
| verify --with-llm-extraction | High — use sparingly |
| run-all | LLM per labeled fixture case |

Use `--limit`, `--stage`, and `--ids` to narrow scope.

## Staging URL

https://staging.arquivodaviolencia.com.br
