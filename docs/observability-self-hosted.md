# Self-hosted observability (Prometheus + Grafana)

Production pipeline metrics are scraped by a dedicated observability VPS and
visualized in Grafana.

| Resource | URL / host |
|----------|------------|
| Grafana dashboard | https://observability.carabetta.xyz/d/arquivo-pipeline |
| Observability VPS | `62.238.12.182` (`/opt/arquivo-observability`) |
| Production scrape targets | `77.42.72.111:8000` (API `/metrics`), `:9091` (worker) |

## Architecture

- **API** (`arquivo-api`) exposes health gauges (`pipeline_worker_alive`,
  `pipeline_redis_connected`, `pipeline_open_failure_issues`, etc.) on `/metrics`
  via `prometheus-fastapi-instrumentator` bound to `REGISTRY`.
- **Worker** (`arquivo-worker`) exposes task/attempt counters on `:9091/metrics`
  via a separate `WORKER_REGISTRY` (cron timestamps, GitHub issue counters, task
  metrics — no duplicate health gauges).
- **Prometheus** on the obs VPS scrapes both targets every 30s.
- **Grafana** is bound to `127.0.0.1:3000` and published via nginx + Let's Encrypt
  at `observability.carabetta.xyz`.

## Local / manual deploy

From your laptop (requires SSH to both VPSes):

```bash
# Set password to match existing Grafana DB (never rotate on redeploy without intent)
export GRAFANA_ADMIN_PASSWORD='…'
bash infra/observability/deploy.sh
```

`deploy.sh` rsyncs `infra/observability/` to the obs VPS, runs `deploy-remote.sh`,
and opens prod UFW for obs → `:8000` / `:9091`.

## CI/CD

Pushing to **`master`** with changes under `infra/observability/**` triggers
[`.github/workflows/deploy-observability.yml`](../.github/workflows/deploy-observability.yml).

Backend metrics deploy via the existing
[`.github/workflows/deploy-backend.yml`](../.github/workflows/deploy-backend.yml)
when `backend/**` or `docker-compose.yml` change.

Observability deploys on **master only** (staging has no scrape targets).

## Dashboard sections

The **Arquivo da Violência - Pipeline** dashboard is organized around three
operational questions:

| Section | Answers |
|---------|---------|
| **Pipeline map** | Item counts at each step (same data as `/admin`) |
| **Where is it stuck?** | Stuck in-flight items, backlog queues, worker/cron health |
| **Failures (24h)** | Count, share %, and cause from `pipeline_attempt` |

Inventory gauges refresh every **5 minutes** from Postgres via the API monitor.

### Metrics reference

| Metric | Registry | Source |
|--------|----------|--------|
| `pipeline_inventory_sources{status}` | API | Live source counts by pipeline status |
| `pipeline_inventory_total` / `_violent_death` / `_raw_events` / `_unique_events` | API | Summary totals matching `/admin` |
| `pipeline_stuck_sources{status}` | API | Items in classifying/downloading/extracting > 15 min |
| `pipeline_attempt_failures_24h{stage,failure_reason}` | API | Failed attempts in last 24h with cause |
| `pipeline_cron_last_success_timestamp{cron}` | Worker | Set when cron task succeeds |
| `pipeline_open_failure_issues` | API | Polled from GitHub every 5 min |

### GitHub Actions secrets

Add in **Settings → Secrets and variables → Actions**:

| Secret | Value / notes |
|--------|----------------|
| `OBS_VPS_HOST` | `62.238.12.182` |
| `OBS_VPS_USER` | `root` |
| `OBS_VPS_SSH_KEY` | Private key with SSH access to obs VPS (can match `VPS_SSH_KEY` if the same key is authorized) |
| `GRAFANA_ADMIN_PASSWORD` | Must match the password in Grafana's volume / `/opt/arquivo-observability/.env` |

Existing secrets reused by the workflow:

| Secret | Used for |
|--------|----------|
| `VPS_HOST` | Production app VPS (`77.42.72.111`) — UFW scrape rules |
| `VPS_USER` | SSH user on prod |
| `VPS_SSH_KEY` | SSH key for prod |

### One-time observability VPS bootstrap

Before the first CI run, on the **observability VPS**:

```bash
# Deploy key or PAT required for private repo
git clone git@github.com:JoaoCarabetta/arquivo-da-violencia.git /root/arquivo-da-violencia

mkdir -p /opt/arquivo-observability
cat >/opt/arquivo-observability/.env <<'EOF'
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<same as GRAFANA_ADMIN_PASSWORD secret>
GRAFANA_DOMAIN=observability.carabetta.xyz
GRAFANA_ROOT_URL=https://observability.carabetta.xyz
EOF
chmod 600 /opt/arquivo-observability/.env

# DNS: observability.carabetta.xyz → 62.238.12.182 (Hostinger)
```

Then add the GitHub secrets above and merge observability changes to `master`.

## Verification

```bash
# Local dev stack
bash scripts/check-observability.sh

# Production API + Grafana + Prometheus series
bash scripts/check-observability.sh --prod
```

Expected on prod after deploy:

- `pipeline_worker_alive{service="api"}` — single series, value `1`
- Worker `:9091` — `pipeline_task_total` present, no `pipeline_worker_alive`
- Grafana dashboard top row — single UP/OK values (no duplicate UP+DOWN)

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Grafana login fails after redeploy | `deploy-remote.sh` overwrote password — ensure `GRAFANA_ADMIN_PASSWORD` secret matches live Grafana DB |
| Duplicate stat values on dashboard | Health gauges scraped from both API and worker — worker must use `WORKER_REGISTRY` only |
| Prometheus targets DOWN | Prod UFW blocking obs IP, or backend not deployed with `METRICS_ENABLED=true` |
| TLS/nginx broken after redeploy | Cert exists but HTTP-only config installed — `deploy-remote.sh` picks HTTPS config when cert is present |
