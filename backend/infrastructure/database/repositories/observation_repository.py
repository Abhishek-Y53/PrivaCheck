"""Persistence operations for short-lived crawler observations."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.infrastructure.database.models.observation import ScanObservation
from backend.schemas.core import Observation


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class ObservationRepository:
    """Store and retrieve temporary crawler observations.

    These rows are staging data. Restrict access to trusted worker/service code,
    delete them after compliance evaluation, and run the expiry cleanup method
    periodically as a backstop. This repository deliberately never commits.
    """

    @staticmethod
    def create_many(
        session: Session,
        scan_id: UUID | str,
        observations: Sequence[Observation],
    ) -> int:
        """Insert observations in their original order and flush the batch."""
        normalized_scan_id = _as_uuid(scan_id)
        rows: list[ScanObservation] = []

        for ordinal, observation in enumerate(observations):
            timestamp = float(observation.timestamp)
            if not math.isfinite(timestamp):
                raise ValueError("Observation timestamp must be finite")
            observed_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            rows.append(
                ScanObservation(
                    scan_id=normalized_scan_id,
                    ordinal=ordinal,
                    category=observation.category,
                    source_url=observation.source_url,
                    observed_at=observed_at,
                    data=observation.data,
                )
            )

        if rows:
            session.add_all(rows)
            session.flush()
        return len(rows)

    @staticmethod
    def list_for_scan(
        session: Session,
        scan_id: UUID | str,
    ) -> list[ScanObservation]:
        """Return a scan's observations in crawler order."""
        statement = (
            select(ScanObservation)
            .where(ScanObservation.scan_id == _as_uuid(scan_id))
            .order_by(ScanObservation.ordinal.asc())
        )
        return list(session.scalars(statement).all())

    @staticmethod
    def count_for_scan(session: Session, scan_id: UUID | str) -> int:
        """Count staged observations without loading their JSONB payloads."""
        statement = select(func.count()).select_from(ScanObservation).where(
            ScanObservation.scan_id == _as_uuid(scan_id)
        )
        return int(session.scalar(statement) or 0)

    @staticmethod
    def delete_for_scan(session: Session, scan_id: UUID | str) -> int:
        """Delete all staging observations for one scan."""
        result = session.execute(
            delete(ScanObservation).where(
                ScanObservation.scan_id == _as_uuid(scan_id)
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    def delete_expired(session: Session) -> int:
        """Delete observations whose 24-hour (or explicitly set) TTL elapsed."""
        result = session.execute(
            delete(ScanObservation).where(
                ScanObservation.expires_at < func.now()
            )
        )
        return int(result.rowcount or 0)
