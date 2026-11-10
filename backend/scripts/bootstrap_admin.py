"""One-time bootstrap of the first verified, Google-linked administrator.

Run only in a trusted local/Compose shell after the target has signed in once.
Refuses to run when any active ADMIN already exists.
"""
from __future__ import annotations

import argparse
from sqlalchemy import select, text

from backend.api.services.auth_service import normalize_email
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.user_session import UserSession
from backend.infrastructure.database.session import SessionLocal


def bootstrap_admin(email: str) -> None:
    normalized = normalize_email(email)
    with SessionLocal() as db:
        with db.begin():
            # PostgreSQL transaction-scoped advisory lock prevents simultaneous bootstrap.
            if db.bind and db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(73492861)"))
            existing_admin = db.scalar(select(User.id).where(User.role == "ADMIN", User.is_active.is_(True)))
            if existing_admin is not None:
                raise RuntimeError("An active administrator already exists; use audited admin management instead.")
            user = db.scalar(select(User).where(User.email == normalized).with_for_update())
            if user is None or not user.google_sub or not user.is_active:
                raise RuntimeError("The target must first sign in through Google as an active approved user.")
            user.role = "ADMIN"
            db.query(UserSession).filter(UserSession.user_id == user.id).delete(synchronize_session=False)
            db.flush()
    print("First administrator bootstrapped. The user must sign in again.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email of an already Google-verified PrivaCheck user")
    args = parser.parse_args()
    bootstrap_admin(args.email)
