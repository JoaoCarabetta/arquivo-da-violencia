# Self-hosted observability (Prometheus + Grafana)

Production pipeline metrics are scraped by a dedicated observability VPS and
visualized in Grafana.

| Resource | URL / host |
|----------|------------|
| Pipeline dashboard | https://observability.carabetta.xyz/d/arquivo-pipeline |
| Host resources dashboard | https://observability.carabetta.xyz/d/arquivo-hosts |
| Observability VPS | `62.238.12.182` (`/opt/arquivo-observability`) |
| Production scrape targets | `77.42.72.111:8000` (API), `:9091` (worker), `:9100` (node_exporter) |
| Observability scrape targets | `node_exporter:9100` (obs VPS host metrics, Docker network) |

## Architecture

- **API** (`arquivo-api`) exposes health gauges (`pipeline_worker_alive`,
  `pipeline_redis_connected`, `pipeline_open_failure_issues`, etc.) on `/metrics`
  via `prometheus-fastapi-instrumentator` bound to `REGISTRY`.
- **Worker** (`arquivo-worker`) exposes task/attempt counters on `:9091/metrics`
  via a separate `WORKER_REGISTRY` (cron timestamps, GitHub issue counters, task
  metrics — no duplicate health gauges).
- **Prometheus** on the obs VPS scrapes application and host targets every 30s.
- **Alertmanager** evaluates firing alerts and routes to **alert-router**, which
  sends Telegram notifications and dispatches the Cursor cloud agent on critical
  alerts only.
- **node_exporter** on prod (`docker-compose.yml`, `:9100`) and on the obs VPS
  (`infra/observability/docker-compose.yml`, internal Docker network) exposes
  RAM, disk, and CPU metrics (`node_memory_*`, `node_filesystem_*`,
  `node_cpu_seconds_total`).
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
and opens prod UFW for obs → `:8000` / `:9091` / `:9100`.

## CI/CD

Pushing to **`master`** with changes under `infra/observability/**` triggers
[`.github/workflows/deploy-observability.yml`](../.github/workflows/deploy-observability.yml).

Backend metrics deploy via the existing
[`.github/workflows/deploy-backend.yml`](../.github/workflows/deploy-backend.yml)
when `backend/**` or `docker-compose.yml` change (includes prod **node_exporter**
on `:9100`).

Observability deploys on **master only** (staging has no scrape targets).

## Dashboards

### Pipeline (`/d/arquivo-pipeline`)

Organized around three operational questions:

| Section | Answers |
|---------|---------|
| **Pipeline map** | Item counts at each step (same data as `/admin`) |
| **Where is it stuck?** | Stuck in-flight items, backlog queues, worker/cron health |
| **Failures (24h)** | Count, share %, and cause from `pipeline_attempt` |

Inventory gauges refresh every **5 minutes** from Postgres via the API monitor.

### Host resources (`/d/arquivo-hosts`)

RAM, root disk, and CPU for **production** (`host=prod`) and **observability**
(`host=obs`) VPSes. Use the **Host** dropdown to filter. Gauges turn yellow/red
at 70–90% thresholds; **Scrape health** shows whether Prometheus reaches each
node_exporter target.

Deploy notes:

- **Obs node_exporter** — ships with `infra/observability/**` (observability CI).
- **Prod node_exporter** — ships with `docker-compose.yml` (backend CI on `master`).
- **Prod UFW :9100** — applied by observability deploy (obs VPS IP only).

### Metrics reference

| Metric | Registry | Source |
|--------|----------|--------|
| `pipeline_inventory_sources{status}` | API | Live source counts by pipeline status |
| `pipeline_inventory_total` / `_violent_death` / `_raw_events` / `_unique_events` | API | Summary totals matching `/admin` |
| `pipeline_stuck_sources{status}` | API | Items in classifying/downloading/extracting > 15 min |
| `pipeline_attempt_failures_24h{stage,failure_reason}` | API | Failed attempts in last 24h with cause |
| `pipeline_cron_last_success_timestamp{cron}` | Worker | Set when cron task succeeds |
| `pipeline_open_failure_issues` | API | Polled from GitHub every 5 min |
| `node_memory_*`, `node_filesystem_*`, `node_cpu_seconds_total` | node_exporter | Host RAM, disk, CPU (labels `host=prod\|obs`) |
| `up{job=~"arquivo-prod-node\|obs-node"}` | Prometheus | Scrape health for node_exporter |

## Alerting

Prometheus alert rules:
[`infra/observability/prometheus/rules/arquivo-alerts.yml`](../infra/observability/prometheus/rules/arquivo-alerts.yml).
Alertmanager routes to **alert-router** (`infra/observability/alert-router/`).

| Severity | Telegram | Cursor agent |
|----------|----------|--------------|
| warning | Yes | No |
| critical | Yes | Yes |

### Critical alerts (Telegram + Cursor agent)

| Alert | Condition |
|-------|-----------|
| `WorkerDown` | `pipeline_worker_alive == 0` for 3m |
| `RedisDisconnected` | `pipeline_redis_connected == 0` for 2m |
| `ApiScrapeDown` / `WorkerScrapeDown` | scrape target down |
| `StuckSourcesCritical` | stuck sources ≥ 5 for 10m |
| `QueueDepthCritical` | queue depth ≥ 50 for 10m |
| `CronIngestStale` | hourly ingest > 120 min ago |
| `HostDiskCritical` / `HostMemoryCritical` | > 90% for 5–10m |
| `ObservabilityScrapeDown` | any prod/obs scrape down 5m |

### Warning alerts (Telegram only)

Stuck sources ≥ 1, queue ≥ 20, classification backlog ≥ 500, heartbeat misses ≥
2, open GitHub failure issues, cron > 90 min, host disk > 75%, memory > 70%,
CPU > 70%.

### Obs VPS alert secrets

One-time setup in `/opt/arquivo-observability/.env` (preserved by
`deploy-remote.sh`):

```bash
TELEGRAM_BOT_TOKEN=…
TELEGRAM_CHAT_ID=…
PIPELINE_HEALTH_WEBHOOK_URL=https://api2.cursor.sh/automations/webhook/…
PIPELINE_HEALTH_WEBHOOK_AUTH=crsr_…
```

Test after deploy:

```bash
bash scripts/test-alert-router.sh --obs warning
bash scripts/test-alert-router.sh --obs critical
```

The 30-minute health script remains for log/SQL checks. See
[`docs/pipeline-auto-remediation.md`](pipeline-auto-remediation.md).

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
TELEGRAM_BOT_TOKEN=<same as prod bot>
TELEGRAM_CHAT_ID=<your chat id>
PIPELINE_HEALTH_WEBHOOK_URL=<Cursor Automation webhook URL>
PIPELINE_HEALTH_WEBHOOK_AUTH=<crsr_… token>
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
- Grafana pipeline dashboard top row — single UP/OK values (no duplicate UP+DOWN)
- `up{job="arquivo-prod-node",host="prod"}` — `1` when prod node_exporter and UFW `:9100` are live
- Host resources dashboard — `prod` and `obs` series when both node_exporter targets scrape

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Grafana login fails after redeploy | `deploy-remote.sh` overwrote password — ensure `GRAFANA_ADMIN_PASSWORD` secret matches live Grafana DB |
| Duplicate stat values on dashboard | Health gauges scraped from both API and worker — worker must use `WORKER_REGISTRY` only |
| Prometheus targets DOWN | Prod UFW blocking obs IP, or backend not deployed with `METRICS_ENABLED=true` |
| Host metrics missing for prod | Prod `node_exporter` not running (`docker compose -p prod ps`) or UFW `:9100` not open for obs IP |
| TLS/nginx broken after redeploy | Cert exists but HTTP-only config installed — `deploy-remote.sh` picks HTTPS config when cert is present |
