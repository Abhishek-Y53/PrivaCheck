from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint

from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models import User, UserSession


def test_user_session_persists_only_hash_and_has_expiration_and_revocation_fields():
    table = UserSession.__table__
    assert set(table.columns.keys()) == {
        "id", "user_id", "token_hash", "created_at", "expires_at", "revoked_at"
    }
    assert table.c.token_hash.type.length == 64
    assert table.c.token_hash.unique is True
    assert table.c.user_id.nullable is False
    assert table.c.expires_at.nullable is False
    assert table.c.revoked_at.nullable is True


def test_user_session_has_user_cascade_and_lookup_index():
    foreign_key = next(iter(UserSession.__table__.c.user_id.foreign_keys))
    assert isinstance(foreign_key, ForeignKey)
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "CASCADE"

    index = next(
        index for index in UserSession.__table__.indexes
        if index.name == "ix_user_sessions_user_id_expires_at"
    )
    assert isinstance(index, Index)
    assert [column.name for column in index.columns] == ["user_id", "expires_at"]


def test_user_and_session_relationships_are_bidirectional_and_registered():
    assert User.sessions.property.back_populates == "user"
    assert UserSession.user.property.back_populates == "sessions"
    assert "user_sessions" in Base.metadata.tables


def test_session_schema_has_token_hash_and_expiration_constraints():
    checks = {
        constraint.name
        for constraint in UserSession.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_user_sessions_token_hash_sha256" in checks
    assert "ck_user_sessions_expires_after_created" in checks
    uniques = {
        constraint.name
        for constraint in UserSession.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "uq_user_sessions_token_hash" in uniques
