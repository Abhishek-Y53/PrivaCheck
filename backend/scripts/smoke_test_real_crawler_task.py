"""End-to-end smoke test for crawler -> compliance -> persisted report.

Requires PostgreSQL, Valkey, the independently running crawler/compliance
workers, Chromium installed for Playwright, and the configured GDPR YAML file.
The temporary scan is deleted only after successful report verification.
"""

from __future__ import annotations

import sys
from uuid import uuid4

from backend.contracts.task_messages import CrawlerScanRequested
from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ObservationRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.messaging.celery_app import (
    CRAWLER_QUEUE,
    celery_app as producer_app,
)

CRAWLER_TASK = "privacheck.crawler.execute_scan"
TEST_URL = "https://example.com/"
CRAWLER_TIMEOUT_SECONDS = 240
COMPLIANCE_TIMEOUT_SECONDS = 180


def main() -> int:
    scan_id = uuid4()
    with SessionLocal() as session:
        with session.begin():
            ScanRepository.create(
                session,
                website=TEST_URL,
                framework="gdpr",
                scan_id=scan_id,
            )

    completed = False
    try:
        message = CrawlerScanRequested(
            scan_id=scan_id,
            target_url=TEST_URL,
            timeout_seconds=180,
        )
        crawler_async_result = producer_app.send_task(
            CRAWLER_TASK,
            args=[message.to_payload()],
            queue=CRAWLER_QUEUE,
            task_id=str(message.message_id),
        )
        crawler_result = crawler_async_result.get(
            timeout=CRAWLER_TIMEOUT_SECONDS,
            propagate=False,
        )
        if not isinstance(crawler_result, dict) or crawler_result.get("status") != "completed":
            raise RuntimeError(f"Crawler task did not complete: {crawler_result!r}")

        observation_count = int(crawler_result.get("observation_count", -1))
        downstream_task_id = str(crawler_result.get("compliance_task_id", ""))
        if observation_count <= 0 or not downstream_task_id:
            raise RuntimeError("Crawler did not stage observations and dispatch compliance.")

        with SessionLocal() as session:
            scan = ScanRepository.get_by_id(session, scan_id)
            staged_count = ObservationRepository.count_for_scan(session, scan_id)
            if scan is None or scan.lifecycle_status != "RUNNING":
                raise RuntimeError("Scan was not RUNNING at the crawler/compliance handoff.")
            if staged_count != observation_count:
                raise RuntimeError(
                    f"Expected {observation_count} staged observations, found {staged_count}."
                )

        compliance_result = producer_app.AsyncResult(downstream_task_id).get(
            timeout=COMPLIANCE_TIMEOUT_SECONDS,
            propagate=False,
        )
        if not isinstance(compliance_result, dict):
            raise RuntimeError(f"Compliance task returned an invalid result: {compliance_result!r}")
        if compliance_result.get("status") not in {"completed", "skipped"} or compliance_result.get("service") != "compliance":
            raise RuntimeError(f"Compliance evaluation did not complete or safely deduplicate: {compliance_result!r}")

        with SessionLocal() as session:
            scan = ScanRepository.get_by_id(session, scan_id)
            persisted_results = CheckResultRepository.list_for_scan(session, scan_id)
            remaining_observations = ObservationRepository.count_for_scan(session, scan_id)
            if scan is None:
                raise RuntimeError("Scan record disappeared during compliance evaluation.")
            if scan.lifecycle_status != "COMPLETED":
                raise RuntimeError(
                    f"Expected COMPLETED lifecycle, got {scan.lifecycle_status}."
                )
            if scan.total_checks != len(persisted_results):
                raise RuntimeError(
                    f"Scan summary reports {scan.total_checks} checks, "
                    f"but {len(persisted_results)} result rows exist."
                )
            if scan.total_checks <= 0:
                raise RuntimeError("Compliance worker persisted no check results.")
            if scan.observation_count != observation_count:
                raise RuntimeError(
                    f"Expected scan observation_count={observation_count}, "
                    f"found {scan.observation_count}."
                )
            if remaining_observations != 0:
                raise RuntimeError(
                    f"Expected observations to be cleaned after report commit, "
                    f"found {remaining_observations}."
                )

        completed = True
        print("Asynchronous crawler-to-compliance integration smoke test passed.")
        print(f"Scan ID: {scan_id}")
        print(f"Crawler worker: {crawler_result.get('worker', 'unknown')}")
        print(f"Observations staged: {observation_count}")
        print(f"Compliance worker: {compliance_result.get('worker', 'unknown')}")
        print(f"Compliance delivery status: {compliance_result.get('status')}")
        print(f"Compliance task ID: {downstream_task_id}")
        print(f"Persisted check results: {len(persisted_results)}")
        print(f"Compliance status: {scan.compliance_status}")
        print(f"Risk score: {scan.risk_score}")
        print(f"Final lifecycle: {scan.lifecycle_status}")
        print("Temporary observations cleaned after successful report commit.")
        return 0
    finally:
        if completed:
            with SessionLocal() as session:
                with session.begin():
                    scan = ScanRepository.get_by_id(session, scan_id)
                    if scan is not None:
                        session.delete(scan)
            print("Temporary smoke-test scan and results deleted.")
        else:
            print(
                f"Smoke-test scan preserved for diagnosis. Scan ID: {scan_id}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    raise SystemExit(main())
