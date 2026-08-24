"""Tests for configurable REQUESTS_PER_MINUTE rate limiting."""

import os
from unittest.mock import patch

import pytest


def test_requests_per_minute_defaults_to_12():
    """When REQUESTS_PER_MINUTE env is unset, defaults to 12 req/min."""
    with patch.dict(os.environ, {}, clear=False):
        # Remove the env var if it exists
        os.environ.pop("REQUESTS_PER_MINUTE", None)
        
        # Force reimport to pick up env var
        import importlib
        from app.services import cities
        importlib.reload(cities)
        
        assert cities.REQUESTS_PER_MINUTE == 12
        assert cities.REQUEST_INTERVAL_SECONDS == pytest.approx(5.0)


def test_requests_per_minute_reads_from_env():
    """When REQUESTS_PER_MINUTE=60, rate is 60 and interval is 1.0s."""
    with patch.dict(os.environ, {"REQUESTS_PER_MINUTE": "60"}):
        # Force reimport to pick up env var
        import importlib
        from app.services import cities
        importlib.reload(cities)
        
        assert cities.REQUESTS_PER_MINUTE == 60
        assert cities.REQUEST_INTERVAL_SECONDS == pytest.approx(1.0)


def test_rate_limiter_uses_configured_rate():
    """AsyncRateLimiter uses the configured REQUESTS_PER_MINUTE."""
    with patch.dict(os.environ, {"REQUESTS_PER_MINUTE": "60"}):
        # Force reimport to pick up env var
        import importlib
        from app.services import cities
        from app.services import ingestion
        importlib.reload(cities)
        importlib.reload(ingestion)
        
        # Reset the global rate limiter so it picks up new config
        ingestion._rate_limiter = None
        
        limiter = ingestion.get_rate_limiter()
        assert limiter.interval == pytest.approx(1.0)


def test_rate_limiter_default_interval():
    """AsyncRateLimiter defaults to 5s interval when env unset."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("REQUESTS_PER_MINUTE", None)
        
        # Force reimport to pick up env var
        import importlib
        from app.services import cities
        from app.services import ingestion
        importlib.reload(cities)
        importlib.reload(ingestion)
        
        # Reset the global rate limiter so it picks up new config
        ingestion._rate_limiter = None
        
        limiter = ingestion.get_rate_limiter()
        assert limiter.interval == pytest.approx(5.0)
