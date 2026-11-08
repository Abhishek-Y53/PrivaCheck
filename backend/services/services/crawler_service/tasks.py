"""Crawler service tasks.

The crawler worker only validates targets, collects browser observations and
stages them for the compliance service. It does not load or evaluate YAML rules.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from backend.contracts.task_messages import (
    ComplianceEvaluationRequested,
    CrawlerScanCompleted,
    CrawlerScanFailed,
    CrawlerScanRequested,
    parse_task_message,
)
from backend.crawler.orchestrator import CrawlerOrchestrator
from backend.infrastructure.database.repositories import (
    ObservationRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.messaging.celery_app import (
    COMPLIANCE_QUEUE,
    celery_app as message_producer,
)
from backend.services.crawler_service.celery_app import crawler_celery_app

logger = logging.getLogger(__name__)

COMPLIANCE_PROBE_TASK = "privacheck.compliance.worker_probe"


def _mark_scan_failed(scan_id: UUID, message: CrawlerScanFailed) -> None:
    """Persist a controlled failure and remove incomplete staging rows."""
    with SessionLocal() as session:
        with session.begin():
            scan = ScanRepository.get_by_id(session, scan_id)
            if scan is None:
                return
            if scan.lifecycle_status in {"QUEUED", "RUNNING"}:
                ScanRepository.set_lifecycle_status(
                    session,
                    scan_id,
                    "FAILED",
                    error_message=f"Crawler failed: {message.failure_code}.",
                )
            ObservationRepository.delete_for_scan(session, scan_id)


def _dispatch_compliance_request(
    *,
    scan_id: UUID,
    framework_id: str,
    observation_count: int,
) -> str:
    """Publish a small control message; observations remain in PostgreSQL."""
    request = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id=framework_id,
        observation_count=observation_count,
    )
    async_result = message_producer.send_task(
        COMPLIANCE_PROBE_TASK,
        args=[request.to_payload()],
        queue=COMPLIANCE_QUEUE,
        task_id=str(request.message_id),
    )
    return str(async_result.id)


def _run_crawler(url: str, timeout_seconds: int):
    async def bounded_run():
        return await asyncio.wait_for(
            CrawlerOrchestrator(url, headless=True).run(),
            timeout=timeout_seconds,
        )

    # Celery tasks are synchronous. asyncio.run owns and closes the event loop
    # used by Playwright for this task execution.
    return asyncio.run(bounded_run())


@crawler_celery_app.task(
    bind=True,
    name="privacheck.crawler.execute_scan",
    ignore_result=False,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_crawler_scan(
    self: Any,
    payload: dict[str, object],
) -> dict[str, object]:
    """Execute a real Playwright crawl and enqueue compliance evaluation.

    PostgreSQL is the handoff store for observations. If a prior delivery staged
    observations but crashed before dispatching the next task, a redelivery
    reuses those rows instead of repeating the browser crawl.
    """
    message = parse_task_message(payload)
    if not isinstance(message, CrawlerScanRequested):
        raise ValueError("Crawler worker received an unsupported message type.")

    scan_id = message.scan_id
    try:
        with SessionLocal() as session:
            with session.begin():
                scan = ScanRepository.get_by_id(session, scan_id)
                if scan is None:
                    raise LookupError("Scan record does not exist.")
                if scan.website != message.target_url:
                    raise ValueError("Crawler message target does not match the scan record.")

                lifecycle = scan.lifecycle_status.upper()
                if lifecycle in {"COMPLETED", "FAILED", "CANCELLED"}:
                    return {
                        "status": "skipped",
                        "reason": "scan_already_terminal",
                        "scan_id": str(scan_id),
                        "lifecycle_status": lifecycle,
                    }
                if lifecycle == "QUEUED":
                    ScanRepository.set_lifecycle_status(session, scan_id, "RUNNING")
                elif lifecycle != "RUNNING":
                    raise ValueError("Scan is not in a runnable lifecycle state.")

                framework_id = scan.framework
                staged_count = ObservationRepository.count_for_scan(session, scan_id)

        reused_staged_observations = staged_count > 0
        if not reused_staged_observations:
            crawler_result = _run_crawler(
                message.target_url,
                message.timeout_seconds,
            )
            crawler_status = str(
                getattr(crawler_result.status, "value", crawler_result.status)
            ).upper()
            if crawler_status != "COMPLETED":
                failure = CrawlerScanFailed(
                    scan_id=scan_id,
                    failure_code="CRAWLER_INTERNAL_ERROR",
                    retryable=False,
                )
                _mark_scan_failed(scan_id, failure)
                return {
                    "status": "failed",
                    "failure": failure.to_payload(),
                    "scan_id": str(scan_id),
                    "worker": str(self.request.hostname or "unknown"),
                }

            with SessionLocal() as session:
                with session.begin():
                    scan = ScanRepository.get_by_id(session, scan_id)
                    if scan is None or scan.lifecycle_status != "RUNNING":
                        raise RuntimeError("Scan state changed during crawler execution.")
                    # Replace as one transaction to make a redelivery safe after
                    # a previous partial handoff.
                    ObservationRepository.delete_for_scan(session, scan_id)
                    staged_count = ObservationRepository.create_many(
                        session,
                        scan_id,
                        crawler_result.observations,
                    )

        completion = CrawlerScanCompleted(
            scan_id=scan_id,
            observation_count=staged_count,
        )
        compliance_task_id = _dispatch_compliance_request(
            scan_id=scan_id,
            framework_id=framework_id,
            observation_count=staged_count,
        )

        return {
            "status": "completed",
            "scan_id": str(scan_id),
            "crawler_event": completion.to_payload(),
            "observation_count": staged_count,
            "reused_staged_observations": reused_staged_observations,
            "compliance_task_id": compliance_task_id,
            "worker": str(self.request.hostname or "unknown"),
        }

    except asyncio.TimeoutError:
        failure = CrawlerScanFailed(
            scan_id=scan_id,
            failure_code="CRAWLER_TIMEOUT",
            retryable=False,
        )
        try:
            _mark_scan_failed(scan_id, failure)
        except Exception:
            logger.exception("Could not persist crawler timeout for scan_id=%s", scan_id)
        return {"status": "failed", "failure": failure.to_payload(), "scan_id": str(scan_id)}
    except Exception:
        logger.exception("Crawler task failed for scan_id=%s", scan_id)
        failure = CrawlerScanFailed(
            scan_id=scan_id,
            failure_code="CRAWLER_INTERNAL_ERROR",
            retryable=False,
        )
        try:
            _mark_scan_failed(scan_id, failure)
        except Exception:
            logger.exception("Could not persist crawler failure for scan_id=%s", scan_id)
        return {"status": "failed", "failure": failure.to_payload(), "scan_id": str(scan_id)}


@crawler_celery_app.task(
    bind=True,
    name="privacheck.crawler.worker_probe",
    ignore_result=False,
)
def crawler_worker_probe(self: Any, payload: dict[str, object]) -> dict[str, str | int]:
    """Validate a crawler request envelope and acknowledge the crawler queue."""
    message = parse_task_message(payload)
    if not isinstance(message, CrawlerScanRequested):
        raise ValueError("Crawler worker received an unsupported message type.")

    return {
        "status": "ok",
        "service": "crawler",
        "schema_version": message.schema_version,
        "message_id": str(message.message_id),
        "scan_id": str(message.scan_id),
        "task_id": str(self.request.id),
        "worker": str(self.request.hostname or "unknown"),
    }
