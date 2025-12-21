# Arquivo da Violência API - v1

FastAPI backend for tracking violence in Rio de Janeiro.

## Tech Stack

- **FastAPI** - Modern async web framework
- **SQLModel** - SQL databases with Pydantic validation
- **ARQ** - Async task queue with Redis
- **Gemini** - LLM for event extraction

## Setup

### Prerequisites

- Python 3.11+
- Redis (for task queue)
- uv (package manager)

### Installation

```bash
# Install dependencies
uv sync

# Copy environment file
cp .env.example .env

# Edit .env with your settings
```

### Running

```bash
# Development server
uv run uvicorn app.main:app --reload

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=app
```

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## Project Structure

```
backend/
├── app/
│   ├── main.py          # FastAPI app factory
│   ├── config.py        # Settings (Pydantic)
│   ├── database.py      # SQLModel engine/session
│   ├── models/          # SQLModel models
│   ├── routers/         # API endpoints
│   ├── services/        # Business logic
│   └── tasks/           # ARQ tasks
├── tests/               # Test suite
└── alembic/             # Database migrations
```

## Pipeline

The data pipeline has 3 stages:

1. **Ingestion** - Fetch news from Google News RSS
2. **Extraction** - Extract content and use LLM to identify events
3. **Enrichment** - Deduplicate events and link to incidents

