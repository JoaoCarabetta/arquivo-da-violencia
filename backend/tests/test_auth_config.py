"""Tests for auth configuration validation and bcrypt login."""

import pytest

import app.auth as auth_module
from app.auth import (
    authenticate_user,
    get_password_hash,
    validate_auth_config,
)


@pytest.fixture(autouse=True)
def reset_auth_module_state():
    auth_module._jwt_secret_key = None
    yield
    auth_module._jwt_secret_key = None


@pytest.fixture
def production_auth_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "super-secure-production-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", get_password_hash("secure-pass"))


def test_validate_auth_config_rejects_disabled_auth_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_AUTH", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "super-secure-production-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", get_password_hash("secure-pass"))

    with pytest.raises(RuntimeError, match="ENABLE_AUTH must be true"):
        validate_auth_config()


def test_validate_auth_config_requires_jwt_secret_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "change-me-in-production")
    monkeypatch.setenv("ADMIN_PASSWORD", get_password_hash("secure-pass"))

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
        validate_auth_config()


def test_validate_auth_config_requires_bcrypt_hashes_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_AUTH", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "super-secure-production-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "plaintext-password")

    with pytest.raises(RuntimeError, match="bcrypt hash"):
        validate_auth_config()


def test_validate_auth_config_accepts_secure_production_config(production_auth_env):
    validate_auth_config()


def test_authenticate_user_accepts_bcrypt_hash(production_auth_env):
    assert authenticate_user("admin", "secure-pass") is True
    assert authenticate_user("admin", "wrong-pass") is False


def test_authenticate_user_allows_plaintext_in_development(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ADMIN_USERNAME", "devadmin")
    monkeypatch.setenv("ADMIN_PASSWORD", "plain-dev-pass")

    assert authenticate_user("devadmin", "plain-dev-pass") is True
