"""Authentication router."""

import os
from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    LoginRequest,
    Token,
    authenticate_user,
    create_access_token,
)
from app.cloudflare_access import (
    is_cf_access_sso_configured,
    validate_cf_access_jwt,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """
    Login endpoint that returns a JWT token.

    Configure credentials via environment variables:
    - ADMIN_USERNAME / ADMIN_PASSWORD (bcrypt hash in staging/production)
    - ADMIN_USERS (comma-separated username:hash pairs)
    """
    if not authenticate_user(request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": request.username},
        expires_delta=access_token_expires,
    )

    return Token(access_token=access_token)


@router.post("/access-sso", response_model=Token)
async def access_sso(
    request: Request,
    cf_access_jwt_assertion: str | None = Header(
        default=None, alias="Cf-Access-Jwt-Assertion"
    ),
):
    """Mint an Arquivo admin JWT after a valid Cloudflare Access session.

    Requires ``Cf-Access-Jwt-Assertion`` (injected by Cloudflare when this path
    is an Access application destination). Email must be allowlisted.
    Does not accept forged email headers alone. Password login remains available
    for local/dev when Access SSO is not configured.
    """
    if not is_cf_access_sso_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudflare Access SSO is not configured",
        )

    assertion = cf_access_jwt_assertion or request.headers.get(
        "Cf-Access-Jwt-Assertion"
    )
    try:
        claims = validate_cf_access_jwt(assertion or "")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cloudflare Access authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Map Access identity to the configured admin username so existing
    # admin JWT checks keep working; keep email in the token for audit.
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    access_token = create_access_token(
        data={
            "sub": admin_username,
            "cf_email": claims.get("email"),
            "auth": "cf_access",
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=access_token)


@router.post("/verify")
async def verify_token(token: str):
    """Verify if a token is valid."""
    from app.auth import decode_access_token

    try:
        token_data = decode_access_token(token)
        return {"valid": True, "username": token_data.username}
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

