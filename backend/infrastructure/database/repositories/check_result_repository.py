"""Persistence operations for sanitized compliance check results."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.infrastructure.database.models.check_result import CheckResultRecord
from backend.schemas.core import CheckResult


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value)).upper()


class CheckResultRepository:
    """Store and retrieve sanitized per-rule assessment outcomes.

    Pass the sanitized results from ``report_builder`` here, never raw rule-engine
    results containing unredacted browser evidence. Methods flush but do not commit.
    """

    @staticmethod
    def create_many(
        session: Session,
        scan_id: UUID | str,
        results: Sequence[CheckResult],
    ) -> int:
        """Insert all check outcomes for a scan."""
        normalized_scan_id = _as_uuid(scan_id)
        rows: list[CheckResultRecord] = []

        for result in results:
            evidence = [item.model_dump(mode="json") for item in result.evidence]
            rows.append(
                CheckResultRecord(
                    scan_id=normalized_scan_id,
                    check_id=result.check_id,
                    name=result.name,
                    status=_enum_value(result.status),
                    severity=_enum_value(result.severity),
                    confidence=float(result.confidence),
                    explanation=result.explanation,
                    recommendation=result.recommendation,
                    evidence=evidence,
                )
            )

        if rows:
            session.add_all(rows)
            session.flush()
        return len(rows)

    @staticmethod
    def replace_for_scan(
        session: Session,
        scan_id: UUID | str,
        results: Sequence[CheckResult],
    ) -> int:
        """Replace a scan's findings, useful for safe report retry handling.

        The delete and insert are part of the caller's transaction. If insertion
        fails, rolling back restores the prior result set.
        """
        normalized_scan_id = _as_uuid(scan_id)
        session.execute(
            delete(CheckResultRecord).where(
                CheckResultRecord.scan_id == normalized_scan_id
            )
        )
        return CheckResultRepository.create_many(
            session, normalized_scan_id, results
        )

    @staticmethod
    def list_for_scan(
        session: Session,
        scan_id: UUID | str,
    ) -> list[CheckResultRecord]:
        """Return all findings for a scan, ordered by rule ID."""
        statement = (
            select(CheckResultRecord)
            .where(CheckResultRecord.scan_id == _as_uuid(scan_id))
            .order_by(CheckResultRecord.check_id.asc())
        )
        return list(session.scalars(statement).all())

    @staticmethod
    def get_for_check(
        session: Session,
        scan_id: UUID | str,
        check_id: str,
    ) -> CheckResultRecord | None:
        """Return one rule result for a scan."""
        statement = select(CheckResultRecord).where(
            CheckResultRecord.scan_id == _as_uuid(scan_id),
            CheckResultRecord.check_id == check_id,
        )
        return session.scalar(statement)

    @staticmethod
    def delete_for_scan(session: Session, scan_id: UUID | str) -> int:
        """Delete all persisted findings for one scan."""
        result = session.execute(
            delete(CheckResultRecord).where(
                CheckResultRecord.scan_id == _as_uuid(scan_id)
            )
        )
        return int(result.rowcount or 0)
