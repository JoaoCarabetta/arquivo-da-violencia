# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (for better caching)
COPY pyproject.toml ./

# Install Python dependencies from pyproject.toml
RUN uv pip install --system .

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p instance logs

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=entrypoints/run.py

# Expose port
EXPOSE 5000

# Set entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "entrypoints.run:app"]

