"""Admin operations: policy validation, serializable role safeguards and audit.

These functions operate on the request's DB session and commit the state change
and its audit event atomically. They never delete users or historical results.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from backend.api.admin_schemas import AdminUserResponse, AdmissionEntryResponse
from backend.api.services.auth_service import normalize_email
from backend.infrastructure.database.models.admin_audit_log import AdminAuditLog
from backend.infrastructure.database.models.platform_access import PlatformAccessDomain, PlatformAccessEmail
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession

# The same advisory lock as bootstrap_admin: no concurrent writers may race
# when counting active administrators. In SQLite the test DB is single writer.
ADMIN_GOVERNANCE_LOCK_ID = 73492861
_DOMAIN = re.compile(r"^(?=.{4,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")


def normalized_domain(value: str) -> str:
    domain = value.strip().lower()
    if not _DOMAIN.fullmatch(domain) or len(domain) > 253:
        raise ValueError("Provide an exact DNS domain without a wildcard or subdomain suffix.")
    if any(len(label) > 63 for label in domain.split(".")):
        raise ValueError("Each DNS label must be at most 63 characters.")
    return domain


def user_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id, email=user.email, display_name=user.display_name,
        role=user.role, is_active=user.is_active,
        google_linked=bool(user.google_sub), created_at=user.created_at,
    )


def audit(db: Session, *, actor: UUID, action: str, kind: str, target: str,
          before: dict | None = None, after: dict | None = None) -> None:
    db.add(AdminAuditLog(
        actor_user_id=actor, action=action, target_type=kind, target_id=target,
        before_data=before, after_data=after,
    ))


def _governance_lock(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": ADMIN_GOVERNANCE_LOCK_ID})


def _validate_actor(db: Session, actor: User) -> None:
    # Re-check inside the same transaction as the write, after acquiring the
    # advisory lock. An admin demoted in another request cannot keep writing.
    active_role = db.scalar(select(User.role).where(User.id == actor.id, User.is_active.is_(True)))
    if active_role != "ADMIN":
        raise HTTPException(status_code=403, detail="Administrator permission is required.")


def _ensure_another_admin(db: Session) -> None:
    remaining = db.scalar(select(func.count(User.id)).where(User.role == "ADMIN", User.is_active.is_(True)))
    if (remaining or 0) <= 1:
        raise HTTPException(status_code=409, detail="The last active administrator cannot be disabled or demoted.")


def change_user(db: Session, actor: User, user_id: UUID, *, field: str, value: str | bool) -> AdminUserResponse:
    if actor.id == user_id:
        raise HTTPException(status_code=409, detail="You cannot change your own role or active status.")
    _governance_lock(db)
    _validate_actor(db, actor)
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if field == "role":
        if value not in ("USER", "ADMIN"):
            raise ValueError("Unsupported role.")
        if value == "ADMIN" and (not target.google_sub or not target.is_active):
            raise HTTPException(status_code=409, detail="An admin must be an active Google-linked account.")
    elif field != "is_active" or not isinstance(value, bool):
        raise ValueError("Unsupported account change.")

    before = {"role": target.role, "is_active": target.is_active}
    if before[field] == value:
        return user_response(target)  # No action and no audit entry needed.
    if target.role == "ADMIN" and target.is_active and (field == "role" or value is False):
        _ensure_another_admin(db)
    setattr(target, field, value)
    # Any change to role/status revokes all sessions; Google must authenticate
    # again. Store revocation, rather than erasing audit-relevant session rows.
    db.execute(update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None),
    ).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, actor=actor.id, action=f"user.{field}.changed", kind="user", target=str(user_id),
          before=before, after={"role": target.role, "is_active": target.is_active})
    db.commit()
    db.refresh(target)
    return user_response(target)


def set_admission(db: Session, actor: User, *, selector_type: str,
                  value: str, is_active: bool) -> AdmissionEntryResponse:
    if selector_type not in ("domains", "emails"):
        raise HTTPException(status_code=404, detail="Unknown admission selector.")
    try:
        normalized = normalized_domain(value) if selector_type == "domains" else normalize_email(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid exact domain or email address.") from None
    # Lock conflicts with admin role updates, and serialize concurrent allowlist
    # edits so a duplicate create cannot corrupt the audit trail.
    _governance_lock(db)
    _validate_actor(db, actor)
    model = PlatformAccessDomain if selector_type == "domains" else PlatformAccessEmail
    column = model.domain if selector_type == "domains" else model.email
    entry = db.scalar(select(model).where(column == normalized).with_for_update())
    if entry is None:
        if not is_active:
            raise HTTPException(status_code=404, detail="No matching admission entry exists.")
        entry = model(**{column.key: normalized, "is_active": True})
        db.add(entry)
        before = None
    else:
        before = {"is_active": entry.is_active}
        if entry.is_active == is_active:
            return AdmissionEntryResponse(id=entry.id, value=normalized, is_active=entry.is_active, created_at=entry.created_at)
        entry.is_active = is_active
    db.flush()
    audit(db, actor=actor.id, action="allowlist.changed", kind=selector_type, target=normalized,
          before=before, after={"is_active": entry.is_active})
    db.commit()
    db.refresh(entry)
    return AdmissionEntryResponse(id=entry.id, value=normalized, is_active=entry.is_active, created_at=entry.created_at)
