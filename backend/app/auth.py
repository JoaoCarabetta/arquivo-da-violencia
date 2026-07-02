"""Authentication and authorization utilities."""

from datetime import datetime, timedelta
from typing import Optional
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from pydantic import BaseModel

INSECURE_JWT_SECRETS = {
    "",
    "change-me-in-production",
    "your-secret-key-change-in-production",
    "staging-secret-key",
    "staging-secret-key-change-me",
    "dev-secret-key-not-for-production",
}

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# HTTP Bearer scheme for JWT
security = HTTPBearer()

_jwt_secret_key: str | None = None


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data."""
    username: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


def get_environment() -> str:
    """Return the deployment environment name."""
    return os.getenv("ENVIRONMENT", "development").lower()


def is_deployed_environment() -> bool:
    """True for staging/production deployments."""
    return get_environment() in {"production", "staging"}


def is_auth_enabled() -> bool:
    """Whether JWT auth is enforced on protected routes."""
    return os.getenv("ENABLE_AUTH", "true").lower() == "true"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _is_bcrypt_hash(value: str) -> bool:
    return value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")


def _verify_credential(plain_password: str, stored_value: str) -> bool:
    if _is_bcrypt_hash(stored_value):
        return verify_password(plain_password, stored_value)
    if is_deployed_environment():
        return False
    return stored_value == plain_password


def _get_admin_credentials() -> dict[str, str]:
    """Load admin username/password or hash pairs from environment."""
    creds: dict[str, str] = {}
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_username and admin_password:
        creds[admin_username] = admin_password
    extra = os.getenv("ADMIN_USERS", "")
    for pair in extra.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        user, pwd = pair.split(":", 1)
        creds[user.strip()] = pwd.strip()
    return creds


def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user with username and password."""
    creds = _get_admin_credentials()
    stored = creds.get(username)
    if stored is None:
        return False
    return _verify_credential(password, stored)


def get_jwt_secret_key() -> str:
    """Return the configured JWT secret, with a dev-only ephemeral fallback."""
    global _jwt_secret_key
    if _jwt_secret_key is not None:
        return _jwt_secret_key

    configured = os.getenv("JWT_SECRET_KEY", "").strip()
    if configured:
        _jwt_secret_key = configured
        return _jwt_secret_key

    if is_deployed_environment():
        raise RuntimeError("JWT_SECRET_KEY must be set in staging/production")

    _jwt_secret_key = secrets.token_urlsafe(32)
    return _jwt_secret_key


def validate_auth_config() -> None:
    """Fail fast when auth is misconfigured for staging/production."""
    environment = get_environment()
    if environment not in {"production", "staging"}:
        return

    if not is_auth_enabled():
        raise RuntimeError("ENABLE_AUTH must be true in staging/production")

    jwt_secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt_secret or jwt_secret in INSECURE_JWT_SECRETS:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be set to a secure value in {environment}"
        )

    creds = _get_admin_credentials()
    if not creds:
        raise RuntimeError(
            f"At least one admin credential must be configured in {environment}"
        )

    for username, stored in creds.items():
        if not _is_bcrypt_hash(stored):
            raise RuntimeError(
                f"Admin password for {username!r} must be a bcrypt hash in {environment}"
            )

    get_jwt_secret_key()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_jwt_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """Decode and verify a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    return token_data


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Dependency to get the current authenticated user from JWT token."""
    if not is_auth_enabled():
        return "dev-user"

    token = credentials.credentials
    token_data = decode_access_token(token)

    if token_data.username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    return token_data.username


def require_admin(username: str = Depends(get_current_user)) -> str:
    """Dependency that requires admin authentication."""
    return username
