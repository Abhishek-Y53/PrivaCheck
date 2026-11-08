from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from backend.infrastructure.database.repositories.scan_repository import ScanRepository


class _Scalars:
    def __init__(self, statement):
        self.statement = statement

    def all(self):
        return []


class _RecordingSession:
    def __init__(self):
        self.statement = None

    def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def scalars(self, statement):
        self.statement = statement
        return _Scalars(statement)


def _sql(statement):
    return str(statement.compile(dialect=postgresql.dialect()))


def test_get_by_id_for_user_scopes_lookup_to_scan_and_owner():
    session = _RecordingSession()
    scan_id = uuid4()
    user_id = uuid4()

    result = ScanRepository.get_by_id_for_user(session, scan_id, user_id)

    assert result is None
    sql = _sql(session.statement)
    assert "scans.id =" in sql
    assert "scans.user_id =" in sql


def test_list_recent_requires_owner_filter_in_query():
    session = _RecordingSession()
    user_id = uuid4()

    results = ScanRepository.list_recent(
        session,
        user_id=user_id,
        limit=15,
        offset=5,
        lifecycle_status="COMPLETED",
    )

    assert results == []
    sql = _sql(session.statement)
    assert "scans.user_id =" in sql
    assert "scans.lifecycle_status =" in sql
    assert "LIMIT" in sql
    assert "OFFSET" in sql


def test_list_recent_rejects_invalid_pagination_before_query():
    session = _RecordingSession()
    try:
        ScanRepository.list_recent(session, user_id=uuid4(), limit=0)
    except ValueError as exc:
        assert "limit must be between" in str(exc)
    else:
        raise AssertionError("invalid limit should be rejected")
    assert session.statement is None
