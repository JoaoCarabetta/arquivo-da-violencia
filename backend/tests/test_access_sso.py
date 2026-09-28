"""Tests for Cloudflare Access admin SSO."""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwt

import app.cloudflare_access as cf_access
from app.auth import get_password_hash
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_cf_cache():
    cf_access.reset_certs_cache_for_tests()
    yield
    cf_access.reset_certs_cache_for_tests()


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_numbers = key.public_key().public_numbers()

    def _int_to_b64(n: int) -> str:
        from jose.utils import base64url_encode

        length = (n.bit_length() + 7) // 8
        return base64url_encode(n.to_bytes(length, "big")).decode("utf-8")

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "kid": "test-kid",
        "alg": "RS256",
        "n": _int_to_b64(public_numbers.n),
        "e": _int_to_b64(public_numbers.e),
    }
    return private_pem, jwk


@pytest.fixture
def access_sso_env(monkeypatch, rsa_keypair):
    _private_pem, jwk = rsa_keypair
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "testadmin")
    monkeypatch.setenv("ADMIN_PASSWORD", get_password_hash("testpass"))
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "carabetta.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD", "test-aud-tag")
    monkeypatch.setenv(
        "CF_ACCESS_ALLOWED_EMAILS",
        "joao@carabetta.xyz,joao.carabetta@gmail.com",
    )

    def fake_fetch():
        return [jwk]

    monkeypatch.setattr(cf_access, "_fetch_certs", fake_fetch)
    return _private_pem


def _make_assertion(private_pem: bytes, email: str = "joao@carabetta.xyz") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "aud": ["test-aud-tag"],
            "email": email,
            "exp": now + timedelta(hours=1),
            "iat": now,
            "iss": "https://carabetta.cloudflareaccess.com",
            "sub": email,
            "type": "app",
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )


@pytest.fixture
async def client(access_sso_env):
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_access_sso_requires_assertion(client):
    response = await client.post("/api/auth/access-sso")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_sso_rejects_forged_email_header_only(client):
    response = await client.post(
        "/api/auth/access-sso",
        headers={"Cf-Access-Authenticated-User-Email": "joao@carabetta.xyz"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_sso_mints_token_with_valid_jwt(client, access_sso_env):
    assertion = _make_assertion(access_sso_env)
    response = await client.post(
        "/api/auth/access-sso",
        headers={"Cf-Access-Jwt-Assertion": assertion},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]

    # Token works on protected pipeline route
    status = await client.get(
        "/api/pipeline/status",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert status.status_code in (200, 503)


@pytest.mark.asyncio
async def test_access_sso_rejects_non_allowlisted_email(client, access_sso_env):
    assertion = _make_assertion(access_sso_env, email="stranger@example.com")
    response = await client.post(
        "/api/auth/access-sso",
        headers={"Cf-Access-Jwt-Assertion": assertion},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_sso_unavailable_when_not_configured(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", get_password_hash("testpass"))
    monkeypatch.delenv("CF_ACCESS_AUD", raising=False)

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/auth/access-sso")
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_pipeline_still_requires_auth_without_sso(client):
    response = await client.get("/api/pipeline/status")
    assert response.status_code == 401
