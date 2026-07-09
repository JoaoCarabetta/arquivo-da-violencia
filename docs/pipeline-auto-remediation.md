# Pipeline auto-monitoring and remediation

Operational guide for the production pipeline health checker and how an agent
(or you) should respond when it fires.

## Components

| Piece | Location | Role |
|-------|----------|------|
| Health script | `scripts/check-pipeline-health.sh` | Runs on VPS; exits 1 when unhealthy |
| GitHub Action | `.github/workflows/pipeline-health.yml` | SSH every 30 min, `--notify` on failure |
| Worker monitor | `backend/app/services/worker_monitor.py` | Telegram when worker heartbeat stops |
| Pipeline API | `GET /api/pipeline/status` (admin) | Worker alive, cron flag, queue depth |
| **Prometheus alerts** | `infra/observability/prometheus/rules/` | Continuous metric-based detection (30s) |
| **Alertmanager + alert-router** | obs VPS `/opt/arquivo-observability` | Routes alerts → Telegram; critical → Cursor agent |

## Alertmanager path (metrics-based)

Prometheus on the observability VPS evaluates alert rules every 30s. Alertmanager
groups and deduplicates, then POSTs to **alert-router**, which:

| Severity | Telegram | Cursor agent |
|----------|----------|--------------|
| **warning** | Yes | No |
| **critical** | Yes | Yes (existing webhook) |

Critical alerts include: worker down, Redis disconnected, scrape down, stuck
sources ≥ 5, queue depth ≥ 50, stale cron, host disk/RAM > 90%.

The health script (30 min) remains for log/SQL checks metrics cannot see.
Both paths may notify on the same incident; Alertmanager `repeat_interval`
limits re-fires.

### One-time: alert secrets on obs VPS

Add to `/opt/arquivo-observability/.env` (preserved across deploys):

```bash
TELEGRAM_BOT_TOKEN=…          # same bot as prod
TELEGRAM_CHAT_ID=…
PIPELINE_HEALTH_WEBHOOK_URL=…   # same Cursor Automation webhook
PIPELINE_HEALTH_WEBHOOK_AUTH=…  # crsr_… token
```

Then redeploy observability (`bash infra/observability/deploy.sh` or merge to
`master`).

Test:

```bash
bash scripts/test-alert-router.sh --obs warning    # Telegram only
bash scripts/test-alert-router.sh --obs critical   # Telegram + Cursor agent
```

See [docs/observability-self-hosted.md](observability-self-hosted.md) for the
full alert rule reference.

## Setup on the VPS

1. Ensure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are in `/root/arquivo-da-violencia/.env` (already used by prod API/worker).

2. Optional — Cursor Automation webhook:
   ```bash
   # In .env on VPS
   PIPELINE_HEALTH_WEBHOOK_URL=https://api2.cursor.sh/automations/webhook/…
   PIPELINE_HEALTH_WEBHOOK_AUTH=crsr_…   # Cursor → Automations → Generate auth header
   ```

   GitHub: repo secret `CURSOR_AUTOMATION_TOKEN` = same `crsr_…` token.

3. Manual test:
   ```bash
   cd /root/arquivo-da-violencia
   bash scripts/check-pipeline-health.sh
   bash scripts/check-pipeline-health.sh --notify   # sends Telegram/webhook only if failing
   bash scripts/check-pipeline-health.sh --remediate --notify
   ```

4. GitHub secrets (already used by deploy): `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`.

## What the health check verifies

| Check | Failure means |
|-------|----------------|
| `curl localhost:8000/health` | API down |
| `arquivo-worker` Docker health | Worker container unhealthy |
| Redis key `arq:queue:health-check` | Worker process not heartbeating |
| Recent `CITIES_PIPELINE` in worker logs (100 min) | Hourly cron did not run (when cron enabled) |
| Active sources but no ingest start log (100 min) | Backlog/classify running without hourly ingest (`backlog_active_but_no_recent_ingest`) |
| Stuck `classifying` / `downloading` / `extracting` > 15 min | Worker crashed mid-batch |
| Classification `errors > 0` in last 2 h logs | Usually Postgres dialect / boolean bug |
| `Maintenance step failed` / `ProgrammingError` in logs | SQL not portable to Postgres |
| `ready_for_classification` ≥ 1500 | Warning only — large backlog |

## Response tiers

### Tier A — Safe auto-remediation (no code change)

Allowed without a PR:

```bash
# Reset stranded transient statuses, clear jammed ARQ locks, restart worker,
# and re-enqueue ingest/classify as needed (covers no_recent_pipeline_run,
# backlog_active_but_no_recent_ingest, arq_queue_jammed, worker_heartbeat_missing)
bash scripts/check-pipeline-health.sh --remediate

# Manual re-enqueue if the script is unavailable
docker compose -p prod exec -T api python - <<'PY'
import asyncio
from arq import create_pool
from arq.connections import RedisSettings

async def main():
    redis = await create_pool(RedisSettings(host="redis", port=6379))
    await redis.enqueue_job("classify_pending_task", 200, 10)
    await redis.enqueue_job("ingest_cities_full_pipeline", None, "1h")

asyncio.run(main())
PY

# Restart worker if heartbeat missing (after deploy)
docker compose -p prod restart worker
```

### Tier B — Code fix → PR to `develop`

When logs show application bugs (examples from Postgres migration):

- `datetime('now', …)` in raw SQL → bound UTC timestamp (`maintenance.py`)
- Integer `0`/`1` for boolean columns → Python `bool` (`classification.py`)
- `StringDataRightTruncationError` → Alembic widen to `TEXT` + re-run migration

Agent workflow:

1. SSH, capture `docker logs arquivo-worker --since 2h` and failing SQL.
2. Branch `fix/pipeline-<issue>` from `develop`.
3. Minimal fix + `gh pr create --base develop`.
4. Wait for staging deploy; run health check on staging port `8001` if needed.
5. Merge to `master` only after staging is green (per `AGENTS.md`).

### Tier C — Production deploy

Never auto-push `master`. CI deploys prod when `master` moves.

## Cursor Automation (webhook + VPS SSH)

Webhook URL is in VPS `.env` as `PIPELINE_HEALTH_WEBHOOK_URL`.

**SSH for the cloud agent (Option A)** — dedicated key `cursor-automation-arquivo-pipeline`:

- Full setup: [docs/cursor-automation-vps-ssh.md](cursor-automation-vps-ssh.md)
- Private key on your Mac: `~/.ssh/cursor_automation_arv` → paste into Cursor secret **`VPS_SSH_KEY`**
- Also set secrets: `VPS_HOST`=`77.42.72.111`, `VPS_USER`=`root`

Automation editor:

- **Trigger:** Webhook (URL above)
- **Tools:** GitHub (PR to `develop`), terminal/SSH using `VPS_SSH_KEY`
- **Instructions:** copy from `docs/cursor-automation-vps-ssh.md`

Webhook JSON fields: `status`, `failures`, `warnings`, `prompt`.

## Useful diagnostics on failure

```bash
ssh hetzner-arv
cd /root/arquivo-da-violencia

bash scripts/check-pipeline-health.sh --json

docker logs arquivo-worker --since 2h | tail -100
docker logs arquivo-api --since 2h | grep -i error | tail -20

docker compose -p prod exec -T postgres psql -U arquivo -d arquivo_prod -c "
SELECT status, COUNT(*) FROM source_google_news
WHERE status IN ('classifying','downloading','extracting','ready_for_classification')
GROUP BY 1 ORDER BY 2 DESC;

SELECT stage, failure_reason, COUNT(*)
FROM pipeline_attempt
WHERE created_at > now() - interval '2 hours' AND outcome = 'failure'
GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10;
"
```

## Tuning

Environment variables (optional, in VPS `.env`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `PIPELINE_HEALTH_MAX_PIPELINE_AGE_MINUTES` | 100 | Max age since last pipeline start |
| `PIPELINE_HEALTH_ACTIVITY_MINUTES` | 30 | Recent worker stage activity window |
| `PIPELINE_HEALTH_STUCK_SOURCE_MINUTES` | 15 | Stuck transient status threshold |
| `PIPELINE_HEALTH_READY_BACKLOG_WARN` | 1500 | Warn when backlog exceeds this |
| `PIPELINE_HEALTH_WEBHOOK_URL` | — | POST JSON alert on failure |

Scheduled checks and `repository_dispatch` type `pipeline-remediate` run
`--remediate` automatically (Tier-A: re-enqueue pipeline, restart worker,
reset stuck sources). Cloud agents without VPS SSH can trigger remediation via:

```bash
gh api repos/JoaoCarabetta/arquivo-da-violencia/dispatches -f event_type=pipeline-remediate
```

Use `pipeline-diagnose` for the same run plus worker/API logs on failure.
