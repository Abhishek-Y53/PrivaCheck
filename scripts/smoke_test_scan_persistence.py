"""PostgreSQL smoke test for persistence through the API scan service.

Run from the project root:
    python -m scripts.smoke_test_scan_persistence

The test uses a fake pipeline (no external website is crawled), verifies that
scan + sanitized findings are persisted, and deletes the test scan afterward.
"""

from __future__ import annotations

import asyncio
from time import time
from uuid import UUID

from backend.api.schemas import ScanRequest
from backend.api.services.persistent_scan_service import PersistentScanService
from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
    ScanReport,
    SeverityLevel,
)


class FakePipeline:
    async def scan(self, url: str, framework: str) -> ScanReport:
        finding = CheckResult(
            check_id="PERSISTENCE-SMOKE-001",
            name="Persistence integration smoke test",
            status=ComplianceStatus.FAIL,
            severity=SeverityLevel.MEDIUM,
            confidence=0.95,
            explanation="Synthetic finding used only to test persistence.",
            recommendation="Remove this synthetic finding by deleting the test scan.",
            evidence=[],
        )
        return ScanReport(
            scan_id="pipeline-generated-id-is-replaced",
            target_url=url,
            overall_status=ComplianceStatus.FAIL,
            total_checks=1,
            passed_checks=0,
            failed_checks=1,
            risk_score=60.0,
            issues=[finding],
            metadata={
                "framework": framework,
                "crawler_status": "COMPLETED",
                "observation_count": 7,
                "persistence_smoke_test": True,
            },
            created_at=time(),
        )


def main() -> None:
    service = PersistentScanService(pipeline=FakePipeline())
    response = asyncio.run(
        service.scan(
            ScanRequest(website="https://example.com/", framework="gdpr")
        )
    )

    scan_id = UUID(response.scan_id or "")
    try:
        with SessionLocal() as session:
            scan = ScanRepository.get_by_id(session, scan_id)
            findings = CheckResultRepository.list_for_scan(session, scan_id)

            assert scan is not None
            assert scan.lifecycle_status == "COMPLETED"
            assert scan.compliance_status == "FAIL"
            assert scan.total_checks == 1
            assert scan.failed_checks == 1
            assert scan.observation_count == 7
            assert len(findings) == 1
            assert findings[0].check_id == "PERSISTENCE-SMOKE-001"

        print("Scan persistence integration smoke test passed.")
        print(f"Persisted scan ID: {scan_id}")
        print("Lifecycle: COMPLETED; compliance status: FAIL")
    finally:
        with SessionLocal() as session:
            with session.begin():
                scan = ScanRepository.get_by_id(session, scan_id)
                if scan is not None:
                    session.delete(scan)
        print("Temporary smoke-test scan and findings deleted.")


if __name__ == "__main__":
    main()
