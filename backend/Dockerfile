# syntax=docker/dockerfile:1

# =============================================================================
# Arquivo da Violência API - Production Dockerfile
# =============================================================================

FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Builder stage - install dependencies
# =============================================================================
FROM base AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev --no-install-project

# =============================================================================
# Production stage
# =============================================================================
FROM base AS production

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Make sure we use the venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/

# Create instance directory for SQLite
RUN mkdir -p /app/instance && chmod 777 /app/instance

# Note: Health checks are defined in docker-compose.yml per service
# API checks HTTP endpoint, Worker checks process existence

# Default command (can be overridden)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

