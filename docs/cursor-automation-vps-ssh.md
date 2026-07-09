# Cursor Automation — VPS SSH (Option A)

Dedicated SSH access for the pipeline-health Cursor Automation cloud agent.

## VPS connection

| Field | Value |
|-------|-------|
| Host | `77.42.72.111` |
| User | `root` |
| App directory | `/root/arquivo-da-violencia` |
| Key comment | `cursor-automation-arquivo-pipeline` |
| Key fingerprint | `SHA256:1GJ+oegKpn66lfVdZ8KA0ahU2o40xJup2w8idCtjl+U` |

Public key is installed in `/root/.ssh/authorized_keys` on the Hetzner VPS.

## One-time: add secrets in Cursor

In **Cursor → Automations → your pipeline automation → Secrets** (or Cloud Agent
secrets), add:

### `VPS_SSH_KEY`

Full private key (including `-----BEGIN OPENSSH PRIVATE KEY-----` lines).

On your Mac, copy to clipboard:

```bash
pbcopy < ~/.ssh/cursor_automation_arv
```

Do **not** commit this file to git. It lives only at `~/.ssh/cursor_automation_arv`
on your machine.

### `VPS_HOST`

```
77.42.72.111
```

### `VPS_USER`

```
root
```

### `GITHUB_TOKEN` (optional, for PRs)

Fine-grained PAT or use the automation’s built-in GitHub integration with repo
write access to `JoaoCarabetta/arquivo-da-violencia`.

## Automation instructions (paste in editor)

```text
You are the on-call agent for Arquivo da Violência production pipeline.

Secrets:
- VPS_SSH_KEY: OpenSSH private key
- VPS_HOST: 77.42.72.111
- VPS_USER: root

When triggered (webhook JSON with status, failures, warnings, prompt):

The `failures` list may contain health-script keys (e.g. `stuck_sources(count=3)`)
or Prometheus alert names (e.g. `WorkerDown`, `HostDiskCritical`). Map each to
the playbook below. Payload may include `"source": "prometheus-alertmanager"`.

1. Write VPS_SSH_KEY to a temp file (mode 600) and SSH:
   ssh -i <keyfile> -o StrictHostKeyChecking=no ${VPS_USER}@${VPS_HOST}

2. On the VPS:
   cd /root/arquivo-da-violencia
   bash scripts/check-pipeline-health.sh --json
   docker logs arquivo-worker --since 2h | tail -150
   docker logs arquivo-api --since 2h | grep -i error | tail -30
   docker compose -p prod exec -T postgres psql -U arquivo -d arquivo_prod -c "
     SELECT stage, failure_reason, COUNT(*) FROM pipeline_attempt
     WHERE created_at > now() - interval '2 hours' AND outcome = 'failure'
     GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10;"

3. Tier A (no code) — map alert/failure to action:
   - stuck_sources / StuckSourcesCritical / StuckSourcesWarning:
     bash scripts/check-pipeline-health.sh --remediate
   - backlog_active_but_no_recent_ingest / no_recent_pipeline_run:
     bash scripts/check-pipeline-health.sh --remediate
     (enqueues ingest_cities_hourly or ingest_cities_full_pipeline)
   - worker_heartbeat_missing / WorkerDown / HeartbeatMissesWarning:
     docker compose -p prod restart worker
   - arq_queue_jammed / QueueDepthCritical:
     bash scripts/check-pipeline-health.sh --remediate
   - HostDiskCritical / HostMemoryCritical:
     df -h; docker system df; prune logs/images if safe
   - ApiScrapeDown / WorkerScrapeDown / ObservabilityScrapeDown:
     docker compose -p prod ps; check UFW and container health
   Do not spam repository_dispatch while other agents are remediating.

4. Tier B (code): branch fix/pipeline-<issue> from develop, minimal fix, PR to develop.
   Never push master directly. Follow AGENTS.md: develop → staging → master.

5. Report: root cause, VPS actions, PR link if any, health check result.

Docs: docs/pipeline-auto-remediation.md
```

## Trigger

- **Type:** Webhook
- **URL:** `PIPELINE_HEALTH_WEBHOOK_URL` in prod VPS `.env` and obs VPS
  `/opt/arquivo-observability/.env` (alert-router uses the same webhook)

## Verify SSH from your machine

```bash
ssh -i ~/.ssh/cursor_automation_arv root@77.42.72.111 'cd /root/arquivo-da-violencia && bash scripts/check-pipeline-health.sh || true'
```

## Rotate key

```bash
ssh-keygen -t ed25519 -f ~/.ssh/cursor_automation_arv -N "" -C "cursor-automation-arquivo-pipeline"
# Add new .pub to VPS authorized_keys; remove old line; update Cursor secret VPS_SSH_KEY
```
