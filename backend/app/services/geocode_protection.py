"""Rate limiting and response caching for the public geocode endpoint."""

from __future__ import annotations

import json
import re
from typing import Any

import redis.asyncio as redis
from fastapi import HTTPException, Request
from loguru import logger

from app.config import get_settings

GEOCODE_RATE_LIMIT = 30
GEOCODE_RATE_WINDOW_SECONDS = 60
GEOCODE_CACHE_TTL_SECONDS = 24 * 60 * 60

EXPORT_RATE_LIMIT = 5
EXPORT_RATE_WINDOW_SECONDS = 60 * 60


def normalize_geocode_query(query: str) -> str:
    """Normalize a geocode query for cache keys (case + whitespace)."""
    normalized = query.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def get_client_ip(request: Request) -> str:
    """Resolve client IP, honoring reverse-proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _get_redis() -> redis.Redis | None:
    try:
        settings = get_settings()
        client = redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        return client
    except Exception as exc:
        logger.warning(f"Geocode protection: Redis unavailable ({exc}); proceeding without cache/rate limit")
        return None


async def get_cached_geocode(normalized_query: str) -> dict[str, Any] | None:
    """Return cached geocode response if present."""
    client = await _get_redis()
    if client is None:
        return None
    try:
        raw = await client.get(f"geocode:cache:{normalized_query}")
        if raw is None:
            return None
        return json.loads(raw)
    finally:
        await client.aclose()


async def cache_geocode_response(normalized_query: str, payload: dict[str, Any]) -> None:
    """Store a geocode response in Redis."""
    client = await _get_redis()
    if client is None:
        return
    try:
        await client.setex(
            f"geocode:cache:{normalized_query}",
            GEOCODE_CACHE_TTL_SECONDS,
            json.dumps(payload),
        )
    finally:
        await client.aclose()


async def _enforce_rate_limit(
    *,
    client_ip: str,
    key_prefix: str,
    limit: int,
    window_seconds: int,
    log_label: str,
    detail_message: str,
) -> None:
    """Increment a per-IP Redis counter and raise 429 when over the limit."""
    client = await _get_redis()
    if client is None:
        return
    try:
        key = f"{key_prefix}:{client_ip}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        if count > limit:
            logger.warning(
                f"{log_label} rate limit exceeded for {client_ip}: {count} requests in window"
            )
            raise HTTPException(status_code=429, detail=detail_message)
    finally:
        await client.aclose()


async def enforce_geocode_rate_limit(client_ip: str) -> None:
    """Increment per-IP counter and raise 429 when over the limit."""
    await _enforce_rate_limit(
        client_ip=client_ip,
        key_prefix="geocode:rate",
        limit=GEOCODE_RATE_LIMIT,
        window_seconds=GEOCODE_RATE_WINDOW_SECONDS,
        log_label="Geocode",
        detail_message=(
            "Limite de consultas de geocodificação excedido. Tente novamente em alguns minutos."
        ),
    )


async def enforce_export_rate_limit(client_ip: str) -> None:
    """Limit CSV/JSON export downloads to a small number per IP per hour."""
    await _enforce_rate_limit(
        client_ip=client_ip,
        key_prefix="export:rate",
        limit=EXPORT_RATE_LIMIT,
        window_seconds=EXPORT_RATE_WINDOW_SECONDS,
        log_label="Export",
        detail_message=(
            "Limite de exportações excedido. Tente novamente em cerca de uma hora."
        ),
    )


def log_geocode_request(
    *,
    client_ip: str,
    query: str,
    cache_hit: bool,
) -> None:
    """Log geocode traffic for monitoring and anomaly detection."""
    logger.info(
        "Geocode request ip={ip} query={query!r} cache_hit={cache_hit}",
        ip=client_ip,
        query=query,
        cache_hit=cache_hit,
    )
