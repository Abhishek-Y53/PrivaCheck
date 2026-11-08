import pytest
from pydantic import ValidationError

from backend.core.config import Settings


def test_production_requires_secure_auth_cookies():
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", AUTH_COOKIE_SECURE=False)

    settings = Settings(ENVIRONMENT="production", AUTH_COOKIE_SECURE=True)
    assert settings.auth_cookie_secure is True


def test_wildcard_cors_is_rejected_for_cookie_authentication():
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS="*")


def test_samesite_none_requires_secure_cookie():
    with pytest.raises(ValidationError):
        Settings(AUTH_COOKIE_SAMESITE="none", AUTH_COOKIE_SECURE=False)
