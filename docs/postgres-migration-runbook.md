# PostgreSQL Migration Runbook

Operational steps for cutover from SQLite to PostgreSQL. Code and compose changes
must be deployed to staging before production.

## Prerequisites

- `POSTGRES_PASSWORD` set in `/root/arquivo-da-violencia/.env`
- PRs merged: dialect-safe code, Alembic fixes, Postgres compose + migration script
- SQLite backup of production data

## Phase A — Staging cutover

### 1. Deploy to staging

Merge to `develop` and wait for CI to deploy staging (`staging-arquivo-*`).

### 2. Start Postgres and run migrations

```bash
cd /root/arquivo-da-violencia
docker compose -p staging -f docker-compose.yml -f docker-compose.staging.yml up -d postgres
docker compose -p staging -f docker-compose.yml -f docker-compose.staging.yml run --rm --no-deps api alembic upgrade head
```

### 3. Migrate SQLite data into `arquivo_staging`

```bash
# Backup prod SQLite (source of truth until cutover)
sqlite3 backend/app/instance/violence.db ".backup '/root/backups/violence-pre-pg-$(date +%Y%m%d).db'"

docker compose -p staging -f docker-compose.yml -f docker-compose.staging.yml run --rm --no-deps api \
  python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url sqlite+aiosqlite:////root/arquivo-da-violencia/backend/app/instance/violence.db \
  --postgres-url "postgresql+asyncpg://arquivo:${POSTGRES_PASSWORD}@postgres:5432/arquivo_staging"
```

Adjust the SQLite path if the backup file is used instead.

### 4. Restart staging stack

```bash
docker compose -p staging -f docker-compose.yml -f docker-compose.staging.yml up -d api worker
curl -sf http://localhost:8001/health
```

### 5. 48h soak checklist

- [ ] Hourly cron completes (`docker logs staging-arquivo-worker | grep CITIES_PIPELINE`)
- [ ] No `database is locked` errors
- [ ] Public API: `curl https://staging.arquivodaviolencia.com.br/api/public/stats`
- [ ] Admin stats-by-hour: `/api/sources/stats/by-hour`
- [ ] Row counts stable after 2+ pipeline runs

```bash
docker compose -p prod exec -T postgres psql -U arquivo -d arquivo_staging -c \
  "SELECT status, COUNT(*) FROM source_google_news GROUP BY status ORDER BY 2 DESC LIMIT 10;"
```

---

## Phase B — Production cutover

Schedule at `:30` or `:45` UTC to avoid overlapping the `:05` cron.

### 1. Pre-cutover backup

```bash
cd /root/arquivo-da-violencia
sqlite3 backend/app/instance/violence.db ".backup '/root/backups/violence-pre-pg-$(date +%Y%m%d_%H%M).db'"
docker compose -p prod exec -T postgres pg_dump -U arquivo -Fc arquivo_prod > /root/backups/arquivo_prod_empty_$(date +%Y%m%d).dump 2>/dev/null || true
```

### 2. Stop prod worker and API

```bash
docker stop --time=120 arquivo-worker arquivo-api
```

### 3. Migrate data

```bash
docker compose -p prod up -d postgres
docker compose -p prod run --rm --no-deps api alembic upgrade head

docker compose -p prod run --rm --no-deps api \
  python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-url sqlite+aiosqlite:////root/arquivo-da-violencia/backend/app/instance/violence.db \
  --postgres-url "postgresql+asyncpg://arquivo:${POSTGRES_PASSWORD}@postgres:5432/arquivo_prod"
```

### 4. Start prod

```bash
docker compose -p prod up -d api worker
curl -sf http://localhost:8000/health
curl -sf http://localhost:8000/api/pipeline/status
```

### 5. Verify pipeline

Trigger one manual full pipeline via admin API and watch worker logs through all stages.

### 6. Rollback (if needed)

```bash
# Revert .env DATABASE_URL to SQLite, restart api/worker
# SQLite backup at /root/backups/violence-pre-pg-*.db
```

Keep SQLite files for **7 days** after successful cutover.

### 7. Post-cutover staging sync

After prod is healthy on Postgres, prod→staging sync uses:

```bash
bash scripts/sync-staging-db.sh
```

(Legacy SQLite sync: `scripts/sync-staging-db-sqlite.sh`)
