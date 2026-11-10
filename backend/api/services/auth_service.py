"""Revocable opaque session management retained after Google-only login."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.session import SessionLocal


@dataclass(frozen=True, slots=True)
class AuthResult:
    user: User
    session_token: str
    expires_at: datetime


def normalize_email(value: str) -> str:
    try:
        validated = validate_email(value.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("A valid email address is required.") from exc
    normalized = validated.normalized.strip().lower()
    if not 3 <= len(normalized) <= 320:
        raise ValueError("Email address length is invalid.")
    return normalized


def hash_session_token(token: str) -> str:
    """Store only a SHA-256 digest of a 256-bit random session secret."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """Session service only: there is no public password login or registration."""

    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self.session_factory = session_factory

    def revoke(self, *, session_token: str) -> None:
        token_hash = hash_session_token(session_token)
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            with session.begin():
                auth_session = session.scalar(
                    select(UserSession)
                    .where(UserSession.token_hash == token_hash)
                    .with_for_update()
                )
                if auth_session is not None and auth_session.revoked_at is None:
                    auth_session.revoked_at = now
                    session.flush()

    @staticmethod
    def _create_session(session: Session, user: User, now: datetime) -> AuthResult:
        # At most five live sessions per account. Evict expired/revoked rows.
        session.execute(
            delete(UserSession).where(
                UserSession.user_id == user.id,
                (UserSession.expires_at <= now) | (UserSession.revoked_at.is_not(None)),
            )
        )
        active = list(session.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            .order_by(UserSession.created_at.desc(), UserSession.id.desc())
            .with_for_update()
        ).all())
        for old in active[4:]:
            session.delete(old)
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(days=settings.AUTH_SESSION_TTL_DAYS)
        session.add(UserSession(user_id=user.id, token_hash=hash_session_token(token), expires_at=expires_at))
        return AuthResult(user=user, session_token=token, expires_at=expires_at)
