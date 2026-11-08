"""Central application settings loaded from environment variables / .env."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "PrivaCheck"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    CRAWLER_TIMEOUT_SECONDS: int = 30
    CRAWLER_HEADLESS: bool = True
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/privacheck"
    )
    DATABASE_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5

    BROKER_URL: str = "redis://localhost:6379/0"
    AUTH_RATE_LIMIT_REDIS_URL: str | None = None

    AUTH_SESSION_TTL_DAYS: int = Field(default=7, ge=1, le=30)
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    AUTH_LOGIN_RATE_LIMIT: int = Field(default=5, ge=1, le=100)
    AUTH_LOGIN_RATE_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)
    AUTH_REGISTER_RATE_LIMIT: int = Field(default=3, ge=1, le=100)
    AUTH_REGISTER_RATE_WINDOW_SECONDS: int = Field(default=3600, ge=1, le=86400)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @model_validator(mode="after")
    def validate_auth_deployment_settings(self) -> "Settings":
        origins = [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must contain exact origins; wildcard is not allowed.")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("Each CORS origin must be an exact HTTP(S) origin.")
        if self.ENVIRONMENT.strip().lower() in {"production", "prod"} and not self.AUTH_COOKIE_SECURE:
            raise ValueError("AUTH_COOKIE_SECURE must be true in production.")
        if self.AUTH_COOKIE_SAMESITE == "none" and not self.AUTH_COOKIE_SECURE:
            raise ValueError("SameSite=None requires AUTH_COOKIE_SECURE=true.")
        return self

    @property
    def auth_cookie_secure(self) -> bool:
        return self.AUTH_COOKIE_SECURE


settings = Settings()
