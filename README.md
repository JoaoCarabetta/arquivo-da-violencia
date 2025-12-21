# Arquivo da Violência

Violence tracking system for Brazilian cities. Automatically ingests news from Google News RSS, extracts structured event data using LLMs, and deduplicates across sources.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│   API       │────▶│   Redis     │
│  (React)    │     │  (FastAPI)  │     │  (Queue)    │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │                   ▼                   ▼
       │            ┌─────────────┐     ┌─────────────┐
       │            │   SQLite    │◀────│   Worker    │
       │            │  (Database) │     │   (ARQ)     │
       └────────────┴─────────────┴─────┴─────────────┘
```

## Quick Start

### 1. Create environment file

```bash
cp env.example .env
```

Edit `.env` and add your Gemini API key:

```env
GEMINI_API_KEY=your-gemini-api-key-here
ENABLE_CRON=false
DEBUG=false
```

### 2. Build and start all services

```bash
docker compose up -d --build
```

### 3. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 4. Access the application

| Service   | URL                    | Description              |
|-----------|------------------------|--------------------------|
| Frontend  | http://localhost       | React dashboard          |
| API       | http://localhost:8000  | FastAPI backend          |
| API Docs  | http://localhost:8000/docs | Swagger documentation |

## Services

### API (FastAPI)

REST API for the frontend and pipeline control.

```bash
# View logs
docker compose logs -f api

# Restart
docker compose restart api
```

### Worker (ARQ)

Background task processor for:
- News ingestion from Google News RSS
- Content downloading with trafilatura
- LLM extraction with Gemini
- Event deduplication

```bash
# View logs
docker compose logs -f worker

# Restart
docker compose restart worker
```

### Redis

Task queue and result storage.

```bash
# Check status
docker compose exec redis redis-cli ping
```

## Pipeline Operations

### Manual Ingestion

Trigger city ingestion via API:

```bash
# Ingest all 52 Brazilian cities (last 1 hour)
curl -X POST http://localhost:8000/api/pipeline/ingest-cities

# Full pipeline: ingest → download → extract
curl -X POST http://localhost:8000/api/pipeline/ingest-cities-pipeline

# Check city statistics
curl http://localhost:8000/api/pipeline/city-stats
```

### Automatic Hourly Ingestion

Enable the cron job by setting `ENABLE_CRON=true` in your `.env`:

```bash
# Edit .env
ENABLE_CRON=true

# Restart worker to apply
docker compose restart worker
```

The worker will run city ingestion at minute :05 of every hour.

### Check Queue Status

```bash
curl http://localhost:8000/api/pipeline/status
```

## City Coverage

The system monitors **52 Brazilian cities**:

- All state capitals (27)
- All cities with 500k+ population
- Major metropolitan areas

Cities that consistently hit the 100-result limit automatically switch to **source-based sharding** (querying each news outlet separately).

## Development

### Docker Development (with Auto-Reload)

For active development with automatic hot-reload:

```bash
# Start with development config (Vite dev server + hot-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Frontend will be available at http://localhost:5173
# Changes to frontend files appear instantly without rebuild
```

**Features:**
- ✅ **Hot Module Replacement (HMR)**: Frontend changes appear instantly
- ✅ **Volume mounts**: Source files synced automatically
- ✅ **No rebuilds needed**: Edit code and see changes immediately
- ✅ **Vite dev server**: Fast development experience

**How it works:**
- Frontend source files are mounted as volumes
- Vite dev server runs inside Docker with HMR enabled
- Edit files in `frontend/src/` → changes appear in browser automatically

**For production builds:**
```bash
# Rebuild and restart frontend
docker compose up -d --build frontend
```

### Local Development (without Docker)

```bash
# Backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Worker (separate terminal)
uv run arq app.tasks.worker.WorkerSettings

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
cd backend
uv run pytest
```

## Configuration

### Environment Variables

| Variable         | Default                                      | Description                    |
|------------------|----------------------------------------------|--------------------------------|
| `GEMINI_API_KEY` | (required)                                   | Google Gemini API key          |
| `ENABLE_CRON`    | `false`                                      | Enable hourly ingestion        |
| `DEBUG`          | `false`                                      | Enable debug logging           |
| `DATABASE_URL`   | `sqlite+aiosqlite:///./instance/violence.db` | Database connection string     |
| `REDIS_URL`      | `redis://localhost:6379`                     | Redis connection string        |

## Data Model

```
SourceGoogleNews  →  RawEvent  →  UniqueEvent
   (news article)    (extracted)   (deduplicated)
```

- **SourceGoogleNews**: Raw news articles from Google News RSS
- **RawEvent**: Structured event data extracted by LLM
- **UniqueEvent**: Deduplicated events with geocoding

## Useful Commands

```bash
# Start all services (production)
docker compose up -d

# Start with development mode (auto-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Stop all services
docker compose down

# View all logs
docker compose logs -f

# Rebuild after code changes (production)
docker compose up -d --build

# Rebuild frontend only
docker compose up -d --build frontend

# Access API container shell
docker compose exec api bash

# Access database
docker compose exec api sqlite3 instance/violence.db

# Clear all data and start fresh
docker compose down -v
docker compose up -d --build
docker compose exec api alembic upgrade head
```

