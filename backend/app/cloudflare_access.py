"""Cloudflare Access JWT validation for admin SSO.

When Access protects a path, Cloudflare injects ``Cf-Access-Jwt-Assertion``.
We verify that JWT against the team JWKS and allowlist the email claim before
minting an Arquivo admin session. Forged ``Cf-Access-Authenticated-User-Email``
headers alone are not enough.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from jose import jwk, jwt
from jose.exceptions import JWTError

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_EMAILS = (
    "joao@carabetta.xyz",
    "joao.carabetta@gmail.com",
)

_certs_cache: dict[str, Any] = {"fetched_at": 0.0, "keys": []}
_CERTS_TTL_SECONDS = 3600


def get_cf_access_team_domain() -> str:
    return os.getenv("CF_ACCESS_TEAM_DOMAIN", "carabetta.cloudflareaccess.com").strip()


def get_cf_access_aud() -> str:
    return os.getenv("CF_ACCESS_AUD", "").strip()


def is_cf_access_sso_configured() -> bool:
    return bool(get_cf_access_aud() and get_cf_access_team_domain())


def get_allowed_access_emails() -> set[str]:
    raw = os.getenv("CF_ACCESS_ALLOWED_EMAILS", "").strip()
    if raw:
        return {e.strip().lower() for e in raw.split(",") if e.strip()}
    return {e.lower() for e in DEFAULT_ALLOWED_EMAILS}


def _fetch_certs() -> list[dict[str, Any]]:
    now = time.time()
    if _certs_cache["keys"] and now - _certs_cache["fetched_at"] < _CERTS_TTL_SECONDS:
        return _certs_cache["keys"]

    team = get_cf_access_team_domain()
    url = f"https://{team}/cdn-cgi/access/certs"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        keys = resp.json().get("keys") or []

    _certs_cache["keys"] = keys
    _certs_cache["fetched_at"] = now
    return keys


def validate_cf_access_jwt(assertion: str) -> dict[str, Any]:
    """Validate a Cf-Access-Jwt-Assertion and return claims.

    Raises ValueError on any validation failure.
    """
    if not assertion or not assertion.strip():
        raise ValueError("missing Cf-Access-Jwt-Assertion")

    aud = get_cf_access_aud()
    team = get_cf_access_team_domain()
    if not aud or not team:
        raise ValueError("CF Access SSO is not configured")

    try:
        header = jwt.get_unverified_header(assertion)
    except JWTError as exc:
        raise ValueError("invalid Access JWT header") from exc

    kid = header.get("kid")
    keys = _fetch_certs()
    key_data = next((k for k in keys if k.get("kid") == kid), None)
    if key_data is None:
        # Refresh once in case of key rotation
        _certs_cache["fetched_at"] = 0.0
        keys = _fetch_certs()
        key_data = next((k for k in keys if k.get("kid") == kid), None)
    if key_data is None:
        raise ValueError("Access JWT kid not found in team certs")

    public_key = jwk.construct(key_data)
    pem = public_key.to_pem().decode("utf-8")
    issuer = f"https://{team}"

    try:
        claims = jwt.decode(
            assertion,
            pem,
            algorithms=["RS256"],
            audience=aud,
            issuer=issuer,
            options={"require_aud": True, "require_exp": True, "require_iss": True},
        )
    except JWTError as exc:
        raise ValueError(f"Access JWT verification failed: {exc}") from exc

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Access JWT missing email claim")
    if email not in get_allowed_access_emails():
        raise ValueError(f"email {email!r} not allowlisted for admin SSO")

    return claims


def reset_certs_cache_for_tests() -> None:
    _certs_cache["fetched_at"] = 0.0
    _certs_cache["keys"] = []
