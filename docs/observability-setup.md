# Observability setup runbook

This runbook covers the one-time manual setup needed after the code/Compose
changes in this repo are deployed. The instrumentation (metrics, push loop,
Promtail) is automatic; alerting and uptime monitoring live in SaaS consoles.

## 1. Grafana Cloud account

1. Sign up at <https://grafana.com> → Free plan (no credit card).
2. From **My Account → Stack**, create a stack (pick the region closest to
   Hetzner, e.g. `eu-west`).
3. Note the **Prometheus** and **Loki** details:
   - Prometheus remote_write URL: `https://<prom-host>/api/prom/push`
   - Loki push URL: `https://<loki-host>/loki/api/v1/push`
   - Username (numeric, same for both)
   - Create an API key (Cloud → Access policies) — reuse it for both.

4. Put these into your `.env` (see `.env.example`):
   ```
   GRAFANA_CLOUD_PROM_URL=...
   GRAFANA_CLOUD_PROM_USER=...
   GRAFANA_CLOUD_PROM_KEY=...
   GRAFANA_CLOUD_LOKI_URL=...
   GRAFANA_CLOUD_LOKI_USER=...
   GRAFANA_CLOUD_LOKI_KEY=...
   ```
5. Restart the api + worker so they pick up the new env:
   ```bash
   docker compose up -d --no-deps api worker
   docker compose --profile logs up -d promtail
   ```
6. In Grafana Cloud → Explore → Prometheus, run `pipeline_worker_alive` — you
   should see data within ~60s.

## 2. Dashboard import

1. Grafana Cloud → Dashboards → **New → Import**.
2. Upload `dashboards/pipeline-overview.json` from this repo.
3. Map the datasource to your Grafana Cloud Prometheus instance when prompted.

## 3. Alert contact point (Telegram)

Grafana Cloud supports Telegram as a native contact point.

1. Create a Telegram bot via @BotFather (or reuse the existing
   `TELEGRAM_BOT_TOKEN` already in your env).
2. Get the chat ID (already in `TELEGRAM_CHAT_ID`).
3. Grafana Cloud → Alerting → **Contact points → Add contact point**:
   - Type: **Telegram**
   - BOT token: your `TELEGRAM_BOT_TOKEN`
   - Chat ID: your `TELEGRAM_CHAT_ID`
   - Name it `telegram-default`.

## 4. Alert rules

Grafana Cloud → Alerting → **Alert rules → New alert rule**. Add each below;
set the evaluation to `1m` and the for-duration as noted. For each, set the
notification to the `telegram-default` contact point.

| Name | PromQL | For | Notes |
|---|---|---|---|
| WorkerDown | `pipeline_worker_alive == 0` | `5m` | Worker process not heartbeating. |
| PipelineStalled | `absent_over_time(pipeline_task_total[1h])` | `5m` | No task ran in the last hour — cron likely dead. |
| TaskFailures | `sum(rate(pipeline_task_total{outcome="failure"}[10m])) > 0` | `5m` | Any task is failing. |
| QueueBacklog | `pipeline_queue_depth > 50` | `10m` | Queue not draining. |
| LLMQuotaDead | `sum(rate(pipeline_attempts_total{failure_reason="llm_quota"}[10m])) > 0` | `0m` | Daily/project quota exhausted — manual intervention. |

## 5. UptimeRobot (external uptime)

Catches the case the whole Hetzner box is unreachable (the worker monitor
can't alert if the API itself is down).

1. Sign up at <https://uptimerobot.com> (Free plan).
2. **Add New Monitor** twice:
   - HTTPS, URL `https://arquivodaviolencia.com.br/api/pipeline/status`, 5 min
   - HTTPS, URL `https://arquivodaviolencia.com.br/health`, 5 min
3. **My Settings → Alert Contacts → Add** → Telegram. Use the BotFather
   token and the chat ID; the webhook URL is shown once you save.
4. Add the contact to both monitors and set "alert after 2 failures".
