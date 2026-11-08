"""Schema-level tests for user and scan ownership models.

These tests do not require a running PostgreSQL instance. Database migration
execution should additionally be verified against PostgreSQL before release.
"""

from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index

from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models import Scan, User
from backend.infrastructure.database.repositories.scan_repository import (
    ScanRepository,
)


def test_user_table_stores_only_password_hash_and_has_account_timestamps():
    table = User.__table__

    assert set(table.columns.keys()) == {
        "id",
        "email",
        "password_hash",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert table.c.email.nullable is False
    assert table.c.password_hash.nullable is False
    assert table.c.password_hash.type.length == 512
    assert table.c.is_active.nullable is False
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True
    assert "password" not in table.c.keys()


def test_user_email_has_database_canonicalization_and_case_insensitive_uniqueness():
    table = User.__table__
    constraints = {
        constraint.name: constraint
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_users_email_canonical" in constraints

    email_index = next(
        index for index in table.indexes if index.name == "uq_users_email_lower"
    )
    assert isinstance(email_index, Index)
    assert email_index.unique is True
    assert "lower" in str(email_index.expressions[0]).lower()


def test_scan_ownership_is_nullable_and_protected_by_restrict_foreign_key():
    table = Scan.__table__
    assert table.c.user_id.nullable is True

    foreign_key = next(iter(table.c.user_id.foreign_keys))
    assert isinstance(foreign_key, ForeignKey)
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "RESTRICT"

    ownership_index = next(
        index
        for index in table.indexes
        if index.name == "ix_scans_user_id_created_at"
    )
    assert [column.name for column in ownership_index.columns] == [
        "user_id",
        "created_at",
    ]


def test_user_and_scan_relationships_are_bidirectional():
    assert Scan.user.property.back_populates == "scans"
    assert User.scans.property.back_populates == "user"


def test_user_model_is_registered_in_alembic_metadata():
    assert "users" in Base.metadata.tables
    assert "scans" in Base.metadata.tables


class _RecordingSession:
    def __init__(self):
        self.added = []
        self.flushed = False

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushed = True


def test_scan_repository_accepts_an_explicit_owner_without_changing_legacy_calls():
    session = _RecordingSession()
    owner_id = uuid4()

    owned_scan = ScanRepository.create(
        session, website="https://example.com", user_id=owner_id
    )
    legacy_scan = ScanRepository.create(session, website="https://example.org")

    assert owned_scan.user_id == owner_id
    assert legacy_scan.user_id is None
    assert session.flushed is True
    assert session.added == [owned_scan, legacy_scan]


def test_user_delete_is_delegated_to_database_restrict_constraint():
    assert User.scans.property.passive_deletes == "all"
