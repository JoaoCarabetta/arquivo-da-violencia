# Agent Guide

Instructions for AI agents working on this repository.

## Deployment flow

Always follow the flow: **local -> develop -> prod**.

1. **local** - develop and test changes on a local/feature branch.
2. **develop** - merge into `develop`. Pushing to `develop` triggers CI/CD
   ([.github/workflows/deploy-backend.yml](.github/workflows/deploy-backend.yml),
   [.github/workflows/deploy-frontend.yml](.github/workflows/deploy-frontend.yml))
   which builds the `:develop` images and deploys to **staging**
   (`staging-arquivo-*`, API on port `8001`,
   https://staging.arquivodaviolencia.com.br). Verify staging before promoting.
3. **prod** - merge `develop` into `master`. Pushing to `master` deploys to
   **production** (`arquivo-*`, API on port `8000`,
   https://arquivodaviolencia.com.br) and then syncs the prod DB to staging.

Never deploy straight to production: changes must pass through `develop`/staging
first.

## Local development (Docker only)

**Always run and test locally inside Docker.** Do not rely on host `npm install`,
`npm run dev`, or bare-metal Python for day-to-day work — use the dev Compose
stack so dependencies, ports, and env match the project.

### Start the dev stack

From the repo root:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.dev.override.yml up -d --build
```

| Service  | URL / port |
|----------|------------|
| Frontend | http://localhost (Vite, hot-reload) |
| API      | http://localhost:8010 |
| Postgres | localhost:5432 (`arquivo_dev` / password `arquivo_dev`) |
| Redis    | localhost:6379 |

Stop:

```bash
docker compose -f docker-compose.dev.yml -f docker-compose.dev.override.yml down
```

Logs:

```bash
docker compose -f docker-compose.dev.yml logs -f frontend api
```

### Run checks inside containers

Frontend build + lint (after code changes):

```bash
docker compose -f docker-compose.dev.yml run --rm --no-deps frontend npm run build
docker compose -f docker-compose.dev.yml run --rm --no-deps frontend npm run lint
```

Rebuild the frontend image when `package.json` / lockfile changes:

```bash
docker compose -f docker-compose.dev.yml build frontend
```

Backend migrations:

```bash
docker compose -f docker-compose.dev.yml exec api alembic upgrade head
```

Copy env vars from [env.example](env.example) into `.env` at the repo root before
starting services that need API keys. Set `POSTGRES_PASSWORD` for the Postgres
service (default dev password: `arquivo_dev`).

Production and staging use PostgreSQL (`arquivo_prod` / `arquivo_staging`).
See [docs/postgres-migration-runbook.md](docs/postgres-migration-runbook.md) for
cutover steps from legacy SQLite.

## Production server (SSH)

Production runs on a Hetzner VPS. SSH is configured locally as **`hetzner-arv`**.

```bash
ssh hetzner-arv
```

| Field | Value |
|-------|-------|
| Host alias | `hetzner-arv` |
| IP | `77.42.72.111` |
| User | `root` |
| Key | `~/.ssh/hetzner_arquivo_violencia_rsa` |
| App directory | `/root/arquivo-da-violencia` |

If the alias is not set up, add this to `~/.ssh/config`:

```
Host hetzner-arv
    HostName 77.42.72.111
    Port 22
    User root
    IdentityFile ~/.ssh/hetzner_arquivo_violencia_rsa
    StrictHostKeyChecking no
```

### Common commands on prod

```bash
cd /root/arquivo-da-violencia

# Service status
docker ps --filter name=arquivo

# Logs
docker logs arquivo-worker --tail 50
docker logs arquivo-api --tail 50

# Health
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/api/pipeline/status

# Pipeline health (see docs/pipeline-auto-remediation.md)
bash scripts/check-pipeline-health.sh
bash scripts/check-pipeline-health.sh --notify --remediate

# One-shot backfill after eval-improvement deploy (see docs/prod-backfill-runbook.md)
bash scripts/run_prod_backfill.sh staging --dry-run
bash scripts/run_prod_backfill.sh prod --execute --since 2026-01-01

# Docker Compose (production stack)
docker compose -p prod ps
docker compose -p prod up -d --no-deps api worker
```

Public site: https://arquivodaviolencia.com.br

## Observability (self-hosted)

Pipeline metrics: Prometheus + Grafana on a dedicated VPS (`62.238.12.182`).

| Resource | URL |
|----------|-----|
| Grafana dashboard | https://observability.carabetta.xyz/d/arquivo-pipeline |
| Stack directory on obs VPS | `/opt/arquivo-observability` |

- **Manual deploy:** `bash infra/observability/deploy.sh` (see [docs/observability-self-hosted.md](docs/observability-self-hosted.md))
- **CI:** [`.github/workflows/deploy-observability.yml`](.github/workflows/deploy-observability.yml) on `master` when `infra/observability/**` changes
- **Health check:** `bash scripts/check-observability.sh --prod`
- **Alerts:** Prometheus rules + Alertmanager on obs VPS → Telegram (all) + Cursor agent (critical). Test: `bash scripts/test-alert-router.sh --obs warning`
- API `/metrics` = health gauges; worker `:9091/metrics` = task metrics only
