"""Authentication and CSRF dependencies for browser API requests."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.session import get_db
from backend.api.services.auth_service import hash_session_token


def session_cookie_name() -> str:
    if settings.auth_cookie_secure:
        return "__Host-privacheck_session"
    return "privacheck_session"


def csrf_cookie_name() -> str:
    if settings.auth_cookie_secure:
        return "__Host-privacheck_csrf"
    return "privacheck_csrf"


def allowed_origins() -> set[str]:
    return {
        item.strip().rstrip("/")
        for item in settings.CORS_ORIGINS.split(",")
        if item.strip()
    }


def _request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if not referer:
        return None
    parsed = urlsplit(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def require_csrf(request: Request) -> None:
    """Require a double-submit token and, when supplied, an allowlisted Origin."""
    origin = _request_origin(request)
    if origin is not None and origin not in allowed_origins():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )

    cookie_token = request.cookies.get(csrf_cookie_name())
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or len(cookie_token) > 256
        or len(header_token) > 256
        or not secrets.compare_digest(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed. Fetch a new CSRF token and retry.",
        )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(session_cookie_name())
    if not token or len(token) > 256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    statement = (
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    )
    user = db.scalar(statement)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user
