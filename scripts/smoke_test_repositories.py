"""Manual PostgreSQL smoke test for the M2 repository layer.

Run from the project root with Docker Compose PostgreSQL available:
    python scripts/smoke_test_repositories.py

All inserted test rows are rolled back at the end.
"""

from __future__ import annotations

from time import time

from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ObservationRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    Observation,
    SeverityLevel,
)


def main() -> None:
    with SessionLocal() as session:
        transaction = session.begin()
        try:
            scan = ScanRepository.create(
                session,
                website="https://example.com/",
                framework="gdpr",
            )
            scan_id = scan.id
            assert scan.lifecycle_status == "QUEUED"

            ScanRepository.set_lifecycle_status(session, scan_id, "RUNNING")
            assert ScanRepository.get_by_id(session, scan_id).lifecycle_status == "RUNNING"

            observations = [
                Observation(
                    category="dom_link",
                    source_url="https://example.com/",
                    timestamp=time(),
                    data={"text": "Privacy Policy", "href": "/privacy"},
                )
            ]
            inserted_observations = ObservationRepository.create_many(
                session, scan_id, observations
            )
            loaded_observations = ObservationRepository.list_for_scan(session, scan_id)
            assert inserted_observations == 1
            assert len(loaded_observations) == 1
            assert loaded_observations[0].category == "dom_link"

            results = [
                CheckResult(
                    check_id="SMOKE-001",
                    name="Repository smoke test",
                    status=ComplianceStatus.PASS,
                    severity=SeverityLevel.INFO,
                    confidence=1.0,
                    explanation="Repository persistence smoke test.",
                    recommendation=None,
                    evidence=observations,
                )
            ]
            inserted_results = CheckResultRepository.create_many(
                session, scan_id, results
            )
            loaded_results = CheckResultRepository.list_for_scan(session, scan_id)
            assert inserted_results == 1
            assert len(loaded_results) == 1
            assert loaded_results[0].check_id == "SMOKE-001"
            assert loaded_results[0].evidence[0]["category"] == "dom_link"

            ScanRepository.update_report_summary(
                session,
                scan_id,
                compliance_status="PASS",
                total_checks=1,
                passed_checks=1,
                failed_checks=0,
                observation_count=1,
                risk_score=0.0,
                report_metadata={"smoke_test": True},
            )
            ScanRepository.set_lifecycle_status(session, scan_id, "COMPLETED")
            loaded_scan = ScanRepository.get_by_id(session, scan_id)
            assert loaded_scan.lifecycle_status == "COMPLETED"
            assert loaded_scan.compliance_status == "PASS"
            assert loaded_scan.total_checks == 1

            print("Repository smoke test passed.")
            print(f"Temporary scan ID: {scan_id}")
            print("The test transaction will now be rolled back.")
        finally:
            transaction.rollback()


if __name__ == "__main__":
    main()
