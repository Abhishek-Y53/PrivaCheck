"""Account registration, login, and revocable session management."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.session import SessionLocal
from backend.security.passwords import (
    hash_password,
    password_hash_needs_rehash,
    verify_password,
)


class AccountAlreadyExistsError(Exception):
    """The normalized email address is already registered."""


class InvalidCredentialsError(Exception):
    """Email/password combination is invalid or the account is inactive."""


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
    """Hash a high-entropy session secret before it is persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# A dummy hash reduces the timing difference between an unknown email and a
# wrong password. It is not associated with an account and is never accepted.
_DUMMY_PASSWORD_HASH = hash_password("This-is-a-dummy-password-never-used")


class AuthService:
    """Synchronous service using the project's existing SQLAlchemy session factory."""

    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal) -> None:
        self.session_factory = session_factory

    def register(self, *, email: str, password: str) -> AuthResult:
        normalized_email = normalize_email(email)
        password_hash = hash_password(password)
        now = datetime.now(timezone.utc)

        try:
            with self.session_factory() as session:
                with session.begin():
                    user = User(email=normalized_email, password_hash=password_hash)
                    session.add(user)
                    session.flush()
                    result = self._create_session(session, user, now)
                    session.flush()
                    return result
        except IntegrityError as exc:
            # The database's unique index is authoritative and protects against
            # concurrent duplicate registrations. Do not disguise unrelated
            # integrity failures as duplicate-email errors.
            if "uq_users_email_lower" in str(exc).lower():
                raise AccountAlreadyExistsError from None
            raise

    def login(self, *, email: str, password: str) -> AuthResult:
        normalized_email = normalize_email(email)
        now = datetime.now(timezone.utc)

        with self.session_factory() as session:
            with session.begin():
                user = session.scalar(
                    select(User).where(User.email == normalized_email).with_for_update()
                )
                candidate_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
                valid_password = verify_password(password, candidate_hash)
                if user is None or not valid_password or not user.is_active:
                    raise InvalidCredentialsError

                if password_hash_needs_rehash(user.password_hash):
                    user.password_hash = hash_password(password)
                    session.flush()

                result = self._create_session(session, user, now)
                session.flush()
                return result

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
        # Keep at most five live sessions per account. Expired and revoked rows
        # are deleted at login; the oldest live sessions are evicted if needed.
        session.execute(
            delete(UserSession).where(
                UserSession.user_id == user.id,
                (UserSession.expires_at <= now) | (UserSession.revoked_at.is_not(None)),
            )
        )
        active_sessions = list(
            session.scalars(
                select(UserSession)
                .where(
                    UserSession.user_id == user.id,
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                )
                .order_by(UserSession.created_at.desc(), UserSession.id.desc())
                .with_for_update()
            ).all()
        )
        for old_session in active_sessions[4:]:
            session.delete(old_session)

        token = secrets.token_urlsafe(32)  # 256 bits of cryptographic randomness.
        expires_at = now + timedelta(days=settings.AUTH_SESSION_TTL_DAYS)
        session_record = UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=expires_at,
        )
        session.add(session_record)
        return AuthResult(user=user, session_token=token, expires_at=expires_at)
