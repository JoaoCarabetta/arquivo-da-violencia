# Arquivo da Violência

A Flask application for tracking violence incidents in Rio de Janeiro using news articles and social media.

## Quick Start with Docker

The easiest way to run this application in production is using Docker:

```bash
# Quick start (creates .env, builds, and starts services)
./docker-start.sh

# Or manually:
docker-compose up -d
```

**For production server deployment**, see:
- [PRODUCTION_TUTORIAL.md](PRODUCTION_TUTORIAL.md) - Complete guide to deploy to a server and expose to the internet (includes Nginx, SSL, and PUBLIC_MODE configuration)
- [DEPLOYMENT.md](DEPLOYMENT.md) - General Docker deployment instructions

## Features

- **Data Pipeline**: Automatically fetches news from Google News RSS
- **Event Extraction**: Uses AI to extract violence incidents from articles
- **Deduplication**: Automatically merges duplicate incidents
- **Web Interface**: Browse and search incidents
- **Scheduled Updates**: Runs data pipeline every 30 minutes (configurable)

## Development

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
# Install dependencies
uv sync

# Run database migrations
uv run python entrypoints/manage.py db_upgrade

# Run the application
uv run python entrypoints/run.py
```

### Running the Pipeline

```bash
# Run full pipeline (fetch -> extract -> enrich)
uv run python entrypoints/manage.py run-all

# Or run stages individually
uv run python entrypoints/manage.py fetch
uv run python entrypoints/manage.py extract
uv run python entrypoints/manage.py enrich
```

## Project Structure

- `app/`: Flask application code
  - `models.py`: Database models
  - `routes.py`: Web routes
  - `services/`: Pipeline services (ingestion, extraction, enrichment)
- `migrations/`: Database migrations (Alembic)
- `scripts/`: Utility scripts
- `tests/`: Test suite

## Configuration

Configuration is done through environment variables. See `.env.example` for available options.

Key settings:
- `PUBLIC_MODE`: Set to `true` to hide admin pages in production
- `GOOGLE_MAPS_API_KEY`: API key for map features (optional)
- `PIPELINE_INTERVAL_MINUTES`: How often to fetch new data (default: 30)

## License

[Add your license here]

