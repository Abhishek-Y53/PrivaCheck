"""Integration smoke test for temporary crawler-observation staging and cleanup.

Run after applying the patch and starting PostgreSQL:
    python -m scripts.smoke_test_observation_handoff
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

from sqlalchemy import delete, func, select

from backend.api.schemas import ScanRequest
from backend.api.services.persistent_scan_service import PersistentScanService
from backend.infrastructure.database.models.check_result import CheckResultRecord
from backend.infrastructure.database.models.observation import ScanObservation
from backend.infrastructure.database.models.scan import Scan
from backend.infrastructure.database.session import SessionLocal
from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    Observation,
    ScanReport,
    SeverityLevel,
)


MARKER = "privacheck-observation-handoff-smoke"


class SyntheticPipeline:
    """Mimics the pipeline and verifies observations are stored before evaluation."""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.staging_verified = False

    async def scan(self, url: str, framework: str = "gdpr", *, observation_sink=None):
        observation = Observation(
            category="cookie",
            source_url=url,
            timestamp=time.time(),
            data={
                "name": "smoke_cookie",
                "value": "temporary-test-value",
                "marker": MARKER,
            },
        )

        if observation_sink is None:
            raise AssertionError("Persistent service did not provide an observation sink.")

        await observation_sink([observation])

        # Prove the row is committed and visible before the synthetic compliance
        # evaluation returns its report.
        with self.session_factory() as session:
            rows = session.scalars(select(ScanObservation)).all()
            self.staging_verified = any(
                row.data.get("marker") == MARKER for row in rows
            )
        if not self.staging_verified:
            raise AssertionError("Observation was not staged before compliance evaluation.")

        result = CheckResult(
            check_id="SMOKE-001",
            name="Observation handoff smoke check",
            status=ComplianceStatus.FAIL,
            severity=SeverityLevel.MEDIUM,
            confidence=0.95,
            explanation="Synthetic smoke-test finding.",
            recommendation="Delete this synthetic test record.",
            evidence=[],
        )

        return ScanReport(
            scan_id="pipeline-generated-id",
            target_url=url,
            overall_status=ComplianceStatus.FAIL,
            total_checks=1,
            passed_checks=0,
            failed_checks=1,
            risk_score=75.0,
            issues=[result],
            metadata={
                "framework": framework,
                "crawler_status": "COMPLETED",
                "observation_count": 1,
            },
            created_at=time.time(),
        )


def main() -> None:
    session_factory = SessionLocal
    pipeline = SyntheticPipeline(session_factory)
    service = PersistentScanService(
        pipeline=pipeline,
        session_factory=session_factory,
    )

    response = asyncio.run(
        service.scan(
            ScanRequest(
                website="https://example.com/",
                framework="gdpr",
            )
        )
    )

    if not response.scan_id:
        raise AssertionError("No persisted scan ID was returned.")

    scan_id = UUID(response.scan_id)
    try:
        with session_factory() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise AssertionError("Persisted scan record was not found.")
            if scan.lifecycle_status != "COMPLETED":
                raise AssertionError(
                    f"Expected COMPLETED, got {scan.lifecycle_status!r}."
                )

            observation_count = session.scalar(
                select(func.count())
                .select_from(ScanObservation)
                .where(ScanObservation.scan_id == scan_id)
            ) or 0
            result_count = session.scalar(
                select(func.count())
                .select_from(CheckResultRecord)
                .where(CheckResultRecord.scan_id == scan_id)
            ) or 0

            if observation_count != 0:
                raise AssertionError(
                    f"Expected raw observations to be cleaned up, found {observation_count}."
                )
            if result_count != 1:
                raise AssertionError(
                    f"Expected one persisted check result, found {result_count}."
                )

        if not pipeline.staging_verified:
            raise AssertionError("The pre-evaluation staging assertion did not run.")

        print("Observation handoff smoke test passed.")
        print(f"Persisted scan ID: {scan_id}")
        print("Observation was visible in PostgreSQL before evaluation.")
        print("Temporary observations were deleted after evaluation.")
        print("One check result and the COMPLETED scan were retained.")
    finally:
        # Remove the successful smoke-test scan and its check result.
        with session_factory() as session:
            with session.begin():
                session.execute(delete(Scan).where(Scan.id == scan_id))


if __name__ == "__main__":
    main()
