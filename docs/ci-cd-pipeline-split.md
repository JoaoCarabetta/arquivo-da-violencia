# CI/CD ownership after Prefect cutover (B3/B4)

Arquivo and the Prefect **pipeline** stack are split. Mixing them on the VPS broke the public site (API lost reliable Postgres reachability when attached to `pipeline_net`).

## Ownership

| Concern | Owner | Location |
|--------|--------|----------|
| Public site, API, ARQ worker image, frontend | **arquivo-da-violencia** | `/root/arquivo-da-violencia`, Compose `-p prod` / `-p staging` |
| Prefect Server, Prefect workers, ingest/full/backlog deployments | **pipeline** stack | `/opt/pipeline`, Compose `-p pipeline` |
| `pipeline_net` Docker network | **pipeline** stack | created by `/opt/pipeline` compose |
| DB `arquivo_prod` / `arquivo_staging` | shared Postgres on Arquivo host | Arquivo compose owns the container; pipeline flows write via DB URL |

## Arquivo GitHub Actions (keep)

- `Deploy Backend` / `Deploy Frontend` — API + SPA only
- `Pipeline Health` — read-only health; when `PIPELINE_ORCHESTRATOR=prefect` it shells into `/opt/pipeline` for Prefect status / `prefect deployment run`
- `Daily ops checkup`, observability, backfill helpers

## Moved / orphan on Arquivo (do not revive here)

These Actions still appear in the Arquivo repo UI but their YAML was removed from `master` (last success ~2026-07). Remmediation for Prefect workers belongs in the **pipeline** repo / `/opt/pipeline` deploys:

- `Pipeline Remediate Once`
- `Pipeline Remediate Hotfix`
- `Pipeline On-Call Remediate`
- `Pipeline Worker Restart Once`
- `Pipeline Enqueue Ingest Once`

Disable or delete them in Arquivo Settings → Actions → Workflows once the pipeline repo has equivalents.

## Networking rule

- `arquivo-api` stays on the Compose **default** network with `postgres` / `redis`.
- Prefect HTTP from the API uses `PREFECT_API_URL` (default `http://host.docker.internal:4200/api` via `extra_hosts: host-gateway`). The pipeline stack should publish Prefect API on the host (loopback/private) if the API must trigger runs.
- Do **not** re-attach `arquivo-api` to `pipeline_net` from Arquivo compose.

## Env cutover

On the VPS `.env` (Arquivo):

- `PIPELINE_ORCHESTRATOR=prefect` — API pipeline routes + health remmediation use Prefect
- `ENABLE_CRON=false` — ARQ cron off; Prefect schedules own ingest
- `PREFECT_API_URL=...` — override if Prefect is not on host `:4200`

## Emergency public-site restore

`scripts/remediate-prod-api-db.sh` + workflow `Remediate Prod API DB` recreate `arquivo-api` on the default network and verify `/api/public/stats`.
