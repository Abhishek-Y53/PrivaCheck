"""Persistence operations for scan lifecycle and report summary records.

Repository methods flush changes but never commit. Transaction boundaries belong
at the application/service layer so scan state and its findings can be written
atomically in one SQLAlchemy transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.infrastructure.database.models.scan import Scan


class InvalidScanTransition(ValueError):
    """Raised when a scan lifecycle transition is not allowed."""


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "QUEUED": {"RUNNING", "FAILED", "CANCELLED"},
    "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}
_TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class ScanRepository:
    """CRUD and lifecycle operations for ``scans``."""

    @staticmethod
    def create(
        session: Session,
        *,
        website: str,
        framework: str = "gdpr",
        scan_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        ruleset_version_id: UUID | str | None = None,
    ) -> Scan:
        values: dict[str, Any] = {
            "website": website,
            "framework": framework,
            "lifecycle_status": "QUEUED",
        }
        if scan_id is not None:
            values["id"] = _as_uuid(scan_id)
        if user_id is not None:
            values["user_id"] = _as_uuid(user_id)
        if ruleset_version_id is not None:
            values["ruleset_version_id"] = _as_uuid(ruleset_version_id)
        scan = Scan(**values)
        session.add(scan)
        session.flush()
        return scan

    @staticmethod
    def get_by_id(session: Session, scan_id: UUID | str) -> Scan | None:
        """Load by ID for trusted internal worker/service operations.

        Public API code must use get_by_id_for_user so ownership is enforced
        in the database query itself.
        """
        return session.get(Scan, _as_uuid(scan_id))

    @staticmethod
    def get_by_id_for_user(
        session: Session, scan_id: UUID | str, user_id: UUID | str
    ) -> Scan | None:
        """Return only a scan owned by the supplied user.

        Missing and foreign-owned IDs both return None to avoid disclosing
        whether another user's scan exists.
        """
        statement = select(Scan).where(
            Scan.id == _as_uuid(scan_id),
            Scan.user_id == _as_uuid(user_id),
        )
        return session.execute(statement).scalar_one_or_none()

    @staticmethod
    def get_by_id_for_update(session: Session, scan_id: UUID | str) -> Scan | None:
        """Fetch and lock one scan row until the caller's transaction ends."""
        statement = (
            select(Scan)
            .where(Scan.id == _as_uuid(scan_id))
            .with_for_update()
        )
        return session.execute(statement).scalar_one_or_none()

    @staticmethod
    def list_recent(
        session: Session,
        *,
        user_id: UUID | str,
        limit: int = 20,
        offset: int = 0,
        lifecycle_status: str | None = None,
    ) -> list[Scan]:
        """List scans belonging to one user, newest first."""
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset cannot be negative")
        statement = (
            select(Scan)
            .where(Scan.user_id == _as_uuid(user_id))
            .order_by(Scan.created_at.desc(), Scan.id.desc())
        )
        if lifecycle_status is not None:
            normalized = lifecycle_status.strip().upper()
            if normalized not in _ALLOWED_TRANSITIONS:
                raise ValueError("Unsupported lifecycle status")
            statement = statement.where(Scan.lifecycle_status == normalized)
        return list(session.scalars(statement.offset(offset).limit(limit)).all())

    @staticmethod
    def set_lifecycle_status(
        session: Session,
        scan_id: UUID | str,
        new_status: str,
        *,
        error_message: str | None = None,
    ) -> Scan:
        normalized = new_status.strip().upper()
        if normalized not in _ALLOWED_TRANSITIONS:
            raise ValueError("Unsupported lifecycle status")
        if error_message is not None and normalized != "FAILED":
            raise ValueError("error_message is only valid when setting FAILED")

        scan = ScanRepository.get_by_id(session, scan_id)
        if scan is None:
            raise LookupError("Scan not found")
        current = scan.lifecycle_status.upper()
        if normalized == current:
            return scan
        if normalized not in _ALLOWED_TRANSITIONS[current]:
            raise InvalidScanTransition(
                f"Cannot transition a scan from {current} to {normalized}"
            )

        now = datetime.now(timezone.utc)
        scan.lifecycle_status = normalized
        scan.updated_at = now
        if normalized == "RUNNING":
            scan.started_at = now
            scan.error_message = None
        if normalized in _TERMINAL_STATUSES:
            scan.completed_at = now
        if normalized == "FAILED":
            scan.error_message = error_message or "The scan could not be completed."
        session.flush()
        return scan

    @staticmethod
    def update_report_summary(
        session: Session,
        scan_id: UUID | str,
        *,
        compliance_status: str,
        total_checks: int,
        passed_checks: int,
        failed_checks: int,
        observation_count: int,
        risk_score: float,
        report_metadata: dict[str, Any],
    ) -> Scan:
        scan = ScanRepository.get_by_id(session, scan_id)
        if scan is None:
            raise LookupError("Scan not found")
        if scan.lifecycle_status.upper() != "RUNNING":
            raise InvalidScanTransition(
                "A report summary can only be saved while a scan is RUNNING"
            )
        normalized_status = compliance_status.strip().upper()
        if normalized_status not in {
            "PASS", "FAIL", "WARNING", "MANUAL_REVIEW", "NOT_APPLICABLE"
        }:
            raise ValueError("Unsupported compliance status")
        if min(total_checks, passed_checks, failed_checks, observation_count) < 0:
            raise ValueError("Report counts cannot be negative")
        if passed_checks + failed_checks > total_checks:
            raise ValueError("Passed and failed checks cannot exceed total checks")
        if not 0.0 <= risk_score <= 100.0:
            raise ValueError("risk_score must be between 0 and 100")

        scan.compliance_status = normalized_status
        scan.total_checks = total_checks
        scan.passed_checks = passed_checks
        scan.failed_checks = failed_checks
        scan.observation_count = observation_count
        scan.risk_score = float(risk_score)
        scan.report_metadata = report_metadata
        scan.updated_at = datetime.now(timezone.utc)
        session.flush()
        return scan
