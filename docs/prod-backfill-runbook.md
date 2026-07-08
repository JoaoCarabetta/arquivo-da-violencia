# Production backfill runbook

One-time cleanup after merging the eval-improvement-loop PR (117/117 gate):
near-duplicate merge + requeue misclassified discarded sources.

**Flow:** staging first → verify → production.

Related code:
- `backend/app/services/backfill.py` — candidate selection + requeue
- `backend/scripts/backfill_prod_cleanup.py` — combined merge + reclassify
- `backend/scripts/backfill_reclassify_discarded.py` — reclassify only
- `backend/scripts/merge_duplicate_events.py` — merge only (existing)
- `scripts/run_prod_backfill.sh` — VPS wrapper

---

## What this fixes

| Issue | Forward fix (deploy) | Backfill (this runbook) |
|-------|----------------------|-------------------------|
| Duplicate `unique_event` rows | Auto-merge on link + batch dedup | One-shot exact + near-dup merge |
| Wrong headline classification | `classification_heuristics` on new articles | Requeue discarded false negatives |
| Wrong extraction on old rows | `extraction_heuristics` on new extractions | Requeued sources re-extract via pipeline |

Existing extracted events are **not** bulk re-extracted unless their source is requeued and processed again.

---

## 1. Deploy to staging

Merge PR to `develop` and wait for CI/CD (staging images on `:develop`).

Verify staging API:

```bash
curl -sf https://staging.arquivodaviolencia.com.br/health
```

SSH:

```bash
ssh hetzner-arv
cd /root/arquivo-da-violencia
git pull origin develop   # or wait for deploy workflow
docker compose -p staging ps
```

---

## 2. Staging dry-run

```bash
cd /root/arquivo-da-violencia
bash scripts/run_prod_backfill.sh staging --dry-run --since 2026-01-01
```

Review output:
- **merge exact / merge near** — `groups_found`, `events_merged` (should be >0 if dupes exist)
- **reclassify** — `by_target_status` counts and sample headlines

Optional JSON audit:

```bash
docker compose -p staging exec -T api \
  python scripts/backfill_prod_cleanup.py --dry-run --since 2026-01-01 --json \
  | tee /tmp/backfill-staging-dry.json
```

Reclassify-only preview:

```bash
docker compose -p staging exec -T api \
  python scripts/backfill_reclassify_discarded.py --dry-run --signal heuristic_true --limit 50
```

---

## 3. Staging execute

**Back up staging DB first** (Postgres dump or Hetzner snapshot).

```bash
bash scripts/run_prod_backfill.sh staging --execute --since 2026-01-01
```

Enqueue pipeline (script prints this block; run it):

```bash
docker compose -p staging exec -T api python - <<'PY'
import asyncio
from arq import create_pool
from arq.connections import RedisSettings

async def main():
    redis = await create_pool(RedisSettings(host="redis", port=6379))
    await redis.enqueue_job("classify_pending_task", 300, 10)
    await redis.enqueue_job("download_classified_task", 200)
    await redis.enqueue_job("extract_ready_task", 100)
    await redis.enqueue_job("batch_enrich_task", 50)

asyncio.run(main())
PY
```

Monitor:

```bash
docker logs staging-arquivo-worker --tail 100 -f
curl -sf http://localhost:8001/api/pipeline/status   # staging API port
docker compose -p staging exec -T api python - <<'PY'
import asyncio
from sqlalchemy import text
from app.database import async_session_maker

async def main():
    async with async_session_maker() as s:
        for label, q in [
            ("ready_for_classification", "SELECT COUNT(*) FROM source_google_news WHERE status='ready_for_classification'"),
            ("ready_for_download", "SELECT COUNT(*) FROM source_google_news WHERE status='ready_for_download'"),
            ("ready_for_extraction", "SELECT COUNT(*) FROM source_google_news WHERE status='ready_for_extraction'"),
            ("discarded", "SELECT COUNT(*) FROM source_google_news WHERE status='discarded'"),
        ]:
            n = (await s.execute(text(q))).scalar_one()
            print(f"{label}: {n}")

asyncio.run(main())
PY
```

Spot-check staging site for obvious duplicate incidents or missing events.

---

## 4. Production

After staging looks good, merge `develop` → `master` (prod deploy + staging DB sync per normal flow).

On prod VPS:

```bash
cd /root/arquivo-da-violencia
bash scripts/run_prod_backfill.sh prod --dry-run --since 2026-01-01
# review, then:
bash scripts/run_prod_backfill.sh prod --execute --since 2026-01-01
# enqueue pipeline jobs (same block as staging, compose -p prod)
```

Health after prod backfill:

```bash
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/api/pipeline/status
bash scripts/check-pipeline-health.sh
```

---

## Candidate signals (reclassify)

| `--signal` | Meaning |
|------------|---------|
| `all` (default) | Death keywords, heuristic-true headlines, stored false negatives |
| `heuristic_true` | Headlines that match new `classification_heuristics` fatal patterns |
| `death_keywords` | Regex keyword match only |
| `false_negative` | `is_violent_death=true` but status `discarded` |

Requeue targets:
- `ready_for_classification` — discarded at headline stage, no body
- `ready_for_download` — stored violent death, no body yet
- `ready_for_extraction` — body already downloaded (>200 chars)

---

## Rollback

- **Merge step** — not easily reversible; restore DB backup if bad merges occurred.
- **Reclassify step** — sources can be manually set back to `discarded` by id if needed:
  ```sql
  UPDATE source_google_news SET status='discarded' WHERE id IN (...);
  ```

---

## Troubleshooting

| Symptom | Action |
|---------|--------|
| `candidates=0` | Widen `--since` or use `--signal death_keywords` |
| Pipeline backlog grows | Increase worker batch limits or run health `--remediate` |
| Dupes remain after merge | Run `find_near_duplicate_events.py --since YYYY-MM-DD` and inspect CSV |
| Wrong requeues | Use `--signal heuristic_true` for narrower set |

---

## Eval regression (optional)

After deploy, confirm gate still passes locally or in CI:

```bash
docker compose -f docker-compose.dev.yml exec api \
  python -m eval.cli improvement run-all --concurrency 4
```

Expected: **117/117 (100%)**.
