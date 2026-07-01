"""Tests for geocode rate limiting and caching."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services.geocode_protection import (
    enforce_geocode_rate_limit,
    get_cached_geocode,
    normalize_geocode_query,
)


class FakeRedis:
    """Minimal async Redis stub for geocode protection tests."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.counters: dict[str, int] = {}
        self.ttl: dict[str, int] = {}

    async def ping(self):
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        self.ttl[key] = ttl

    async def incr(self, key: str):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int):
        self.ttl[key] = seconds

    async def aclose(self):
        return None


@pytest.fixture
def fake_redis():
    return FakeRedis()


def test_normalize_geocode_query_handles_case_and_whitespace():
    assert normalize_geocode_query("  São   Paulo  ") == "são paulo"
    assert normalize_geocode_query("RIO DE JANEIRO") == "rio de janeiro"


@pytest.mark.asyncio
async def test_get_cached_geocode_returns_payload(fake_redis):
    fake_redis.store["geocode:cache:rio"] = '{"latitude": -22.9, "longitude": -43.2}'

    with patch(
        "app.services.geocode_protection._get_redis",
        AsyncMock(return_value=fake_redis),
    ):
        cached = await get_cached_geocode("rio")

    assert cached == {"latitude": -22.9, "longitude": -43.2}


@pytest.mark.asyncio
async def test_enforce_geocode_rate_limit_allows_under_limit(fake_redis):
    with patch(
        "app.services.geocode_protection._get_redis",
        AsyncMock(return_value=fake_redis),
    ):
        for _ in range(30):
            await enforce_geocode_rate_limit("1.2.3.4")


@pytest.mark.asyncio
async def test_enforce_geocode_rate_limit_blocks_over_limit(fake_redis):
    with patch(
        "app.services.geocode_protection._get_redis",
        AsyncMock(return_value=fake_redis),
    ):
        for _ in range(30):
            await enforce_geocode_rate_limit("1.2.3.4")

        with pytest.raises(HTTPException) as exc:
            await enforce_geocode_rate_limit("1.2.3.4")

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_geocode_endpoint_uses_cache(fake_redis):
    fake_redis.store["geocode:cache:são paulo"] = (
        '{"latitude": -23.5, "longitude": -46.6, "label": "São Paulo", '
        '"source": "cache", "query": "São Paulo", "zoom": 10}'
    )
    app = create_app()

    with patch(
        "app.services.geocode_protection._get_redis",
        AsyncMock(return_value=fake_redis),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/public/geocode", params={"q": "São Paulo"})

    assert response.status_code == 200
    assert response.json()["source"] == "cache"


@pytest.mark.asyncio
async def test_geocode_endpoint_returns_429_when_rate_limited(fake_redis):
    fake_redis.counters["geocode:rate:127.0.0.1"] = 31
    app = create_app()

    with patch(
        "app.services.geocode_protection._get_redis",
        AsyncMock(return_value=fake_redis),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/public/geocode", params={"q": "Curitiba"})

    assert response.status_code == 429
