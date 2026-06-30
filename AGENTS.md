# AGENTS.md

## Cursor Cloud specific instructions

This project ("Arquivo da Violência") is a FastAPI + ARQ backend with a React/Vite frontend, backed by SQLite and Redis. The README documents a Docker Compose dev flow, but Docker is **not** installed in the Cloud VM, so services are run **natively**. The startup update script already installs deps (`uv sync` for `backend/`, `npm ci` for `frontend/`); `uv` and `redis-server` are pre-installed in the VM image.

### Services (run natively, all in dev/hot-reload mode)

| Service | Dir | Start command | Port |
|---|---|---|---|
| Redis | – | `redis-server --daemonize yes` (data dump writes to cwd; start from a scratch dir) | 6379 |
| API (FastAPI) | `backend/` | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` | 8000 |
| Worker (ARQ) | `backend/` | `uv run arq app.tasks.worker.WorkerSettings` | – |
| Frontend (Vite) | `frontend/` | `npm run dev -- --host 0.0.0.0 --port 5173` | 5173 |

Lint/test/build commands are standard and live in `backend/pyproject.toml` and `frontend/package.json`:
`uv run ruff check .`, `uv run pytest` (in `backend/`); `npm run lint`, `npm run build` (in `frontend/`).

### Non-obvious gotchas (important)

- **Some settings are read via `os.getenv`, NOT the `.env` file.** `app/config.py` (pydantic) loads `.env`, but `app/auth.py` and `app/tasks/worker.py` use `os.getenv` directly. So `ENABLE_AUTH`, `ENABLE_CRON`, `JWT_SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` only take effect when exported as real env vars on the API/worker process. When running natively, export the same dev values that `docker-compose.dev.yml` sets, e.g.:
  `ENABLE_AUTH=false ENABLE_CRON=false JWT_SECRET_KEY=dev-secret-key-not-for-production ADMIN_USERNAME=admin ADMIN_PASSWORD=admin123`.
  (Do **not** set `CORS_ORIGINS` to an empty string — pydantic fails to parse it. Leave it unset to use the default list, which already includes `http://localhost:5173`.)
- **The Vite dev proxy targets `http://api:8000`** (a Docker service name, hardcoded in `frontend/vite.config.ts`). For native dev the host `api` must resolve to the API. The VM image maps it in `/etc/hosts` (`127.0.0.1 api`); if admin pages return 500s, re-add `echo "127.0.0.1 api" | sudo tee -a /etc/hosts`. The frontend calls the API via the relative `/api` path through this proxy, so CORS is not exercised in dev.
- **SQLite path is relative to the process cwd** (`./instance/violence.db`). Run `alembic` and `uvicorn` from `backend/` so they share `backend/instance/violence.db`. If the DB is missing, create it with: `cd backend && uv run alembic upgrade head`. The `.db` file is gitignored but persists in the VM snapshot.
- **Admin panel requires a login even when `ENABLE_AUTH=false`** (the frontend route guard always needs a token in `localStorage`). Log in at `/admin/login` with `admin` / `admin123` (the backend defaults). The public site at `/` needs no login.
- **The classify / download / extract / enrich pipeline stages call Google Gemini** and require `GEMINI_API_KEY`; geocoding additionally needs `GOOGLE_MAPS_API_KEY`. Without keys, the **ingest** stage still works (scrapes Google News RSS into the `source_google_news` table), but classify/extract jobs error out. Trigger a pipeline run from the admin dashboard or `POST /api/pipeline/ingest?query=...&when=7d`.
- `frontend/node_modules` was previously committed to git by mistake (it is listed in `.gitignore`); it has been untracked. Use `npm ci` for a clean, reproducible install.
