"""Google subject identities, admission policies, and safe legacy-account linking."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.api.services.auth_service import AuthResult, AuthService
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.session import SessionLocal
from backend.security.google_oidc import GoogleIdentity
from backend.security.passwords import verify_password


class AdmissionDenied(Exception):
    """Identity does not currently meet platform admission policy."""


class LegacyLinkRequired(Exception):
    """A local account exists; prove ownership before linking Google subject."""


class LegacyLinkDenied(Exception):
    """Incorrect password, conflicting Google identity, or inactive account."""


def admitted_user(db: Session, user: User) -> bool:
    """Evaluate *current* allowlist on every authenticated request."""
    if not user.is_active or not user.google_sub:
        return False
    if user.role == "ADMIN":
        return True  # Admin still requires a live account and linked Google identity.
    email_allowed = db.scalar(
        select(exists().where(PlatformAccessEmail.email == user.email, PlatformAccessEmail.is_active.is_(True)))
    )
    if email_allowed:
        return True
    domain = user.email.rsplit("@", 1)[-1]
    if not user.google_hd or user.google_hd != domain:
        return False
    return bool(db.scalar(
        select(exists().where(PlatformAccessDomain.domain == domain, PlatformAccessDomain.is_active.is_(True)))
    ))


class GoogleAuthService(AuthService):
    def __init__(self, session_factory: sessionmaker[Session] = SessionLocal):
        super().__init__(session_factory=session_factory)

    def sign_in(self, identity: GoogleIdentity) -> AuthResult:
        now = datetime.now(timezone.utc)
        try:
            with self.session_factory() as db:
                with db.begin():
                    user = db.scalar(select(User).where(User.google_sub == identity.sub).with_for_update())
                    if user is None:
                        # Never link using only matching email strings.
                        existing = db.scalar(select(User).where(User.email == identity.email).with_for_update())
                        if existing is not None:
                            if not existing.is_active or existing.google_sub is not None:
                                raise AdmissionDenied
                            raise LegacyLinkRequired
                        user = User(
                            email=identity.email, google_sub=identity.sub, google_hd=identity.hd,
                            display_name=identity.name, password_hash=None, role="USER",
                        )
                        db.add(user)
                        db.flush()
                        if not admitted_user(db, user):
                            raise AdmissionDenied
                    else:
                        if not user.is_active:
                            raise AdmissionDenied
                        # Stable sub, not mutable email, identifies this account.
                        if user.email != identity.email:
                            conflict = db.scalar(select(User.id).where(User.email == identity.email))
                            if conflict is not None:
                                raise AdmissionDenied
                            user.email = identity.email
                        user.google_hd = identity.hd
                        user.display_name = identity.name
                        user.password_hash = None  # Google-only accounts cannot retain password login.
                        if not admitted_user(db, user):
                            raise AdmissionDenied
                    result = self._create_session(db, user, now)
                    db.flush()
                    return result
        except IntegrityError as exc:
            # A racing new-account login cannot create two users for one subject.
            raise AdmissionDenied from exc

    def link_legacy(self, *, identity: GoogleIdentity, old_password: str) -> AuthResult:
        now = datetime.now(timezone.utc)
        try:
            with self.session_factory() as db:
                with db.begin():
                    user = db.scalar(select(User).where(User.email == identity.email).with_for_update())
                    if user is None or not user.is_active or user.google_sub is not None or not user.password_hash:
                        raise LegacyLinkDenied
                    if not verify_password(old_password, user.password_hash):
                        raise LegacyLinkDenied
                    claimed = db.scalar(select(User.id).where(User.google_sub == identity.sub))
                    if claimed is not None:
                        raise LegacyLinkDenied
                    # Check eligibility before changing the historical account.
                    user.google_sub = identity.sub
                    user.google_hd = identity.hd
                    user.display_name = identity.name
                    if not admitted_user(db, user):
                        raise AdmissionDenied
                    user.password_hash = None  # No password login after linking.
                    user.role = "USER"  # First migration never grants an admin role.
                    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
                    result = self._create_session(db, user, now)
                    db.flush()
                    return result
        except IntegrityError as exc:
            raise LegacyLinkDenied from exc
