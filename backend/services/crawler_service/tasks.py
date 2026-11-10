"""Crawler service tasks.

The crawler worker only validates targets, collects browser observations and
stages them for the compliance service. It does not load or evaluate YAML rules.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from kombu.exceptions import OperationalError as KombuOperationalError
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)
from sqlalchemy.exc import InterfaceError, OperationalError as SQLAlchemyOperationalError

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

COMPLIANCE_EVALUATION_TASK = "privacheck.compliance.evaluate_scan"


def _mark_scan_failed(
    scan_id: UUID,
    message: CrawlerScanFailed,
    *,
    delete_observations: bool = True,
) -> None:
    """Persist a controlled failure; optionally retain staged evidence for diagnosis."""
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
            if delete_observations:
                ObservationRepository.delete_for_scan(session, scan_id)


def _dispatch_compliance_request(
    *,
    scan_id: UUID,
    framework_id: str,
    observation_count: int,
    ruleset_version_id: UUID | None = None,
) -> str:
    """Publish a small control message; observations remain in PostgreSQL."""
    request = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id=framework_id,
        observation_count=observation_count,
        ruleset_version_id=ruleset_version_id,
    )
    async_result = message_producer.send_task(
        COMPLIANCE_EVALUATION_TASK,
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
    max_retries=3,
    default_retry_delay=5,
    shared=False,
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
    staged_count = 0
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
                ruleset_version_id = getattr(scan, "ruleset_version_id", None)
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
                _mark_scan_failed(scan_id, failure, delete_observations=True)
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
            ruleset_version_id=ruleset_version_id,
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

    except asyncio.TimeoutError as exc:
        retries = int(self.request.retries or 0)
        if retries < int(self.max_retries):
            raise self.retry(
                exc=exc,
                countdown=min(5 * (2 ** retries), 30),
            )
        failure = CrawlerScanFailed(
            scan_id=scan_id,
            failure_code="CRAWLER_TIMEOUT",
            retryable=False,
        )
        _mark_scan_failed(scan_id, failure, delete_observations=True)
        return {
            "status": "failed",
            "failure": failure.to_payload(),
            "scan_id": str(scan_id),
        }
    except (
        SQLAlchemyOperationalError,
        InterfaceError,
        KombuOperationalError,
        RedisConnectionError,
        RedisTimeoutError,
    ) as exc:
        # If the browser result was already staged, a retry reuses the rows and
        # only repeats the downstream publish. This avoids another browser crawl.
        retries = int(self.request.retries or 0)
        if retries < int(self.max_retries):
            raise self.retry(
                exc=exc,
                countdown=min(5 * (2 ** retries), 30),
            )
        failure = CrawlerScanFailed(
            scan_id=scan_id,
            failure_code="CRAWLER_INTERNAL_ERROR",
            retryable=False,
        )
        _mark_scan_failed(
            scan_id,
            failure,
            delete_observations=False,
        )
        logger.exception(
            "Crawler infrastructure retries exhausted for scan_id=%s",
            scan_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return {
            "status": "failed",
            "failure": failure.to_payload(),
            "scan_id": str(scan_id),
        }
    except Exception:
        logger.exception("Crawler task failed for scan_id=%s", scan_id)
        failure = CrawlerScanFailed(
            scan_id=scan_id,
            failure_code="CRAWLER_INTERNAL_ERROR",
            retryable=False,
        )
        try:
            # Keep already-staged evidence if the failure happened during
            # handoff; the normal TTL cleanup remains the backstop.
            _mark_scan_failed(
                scan_id,
                failure,
                delete_observations=(staged_count == 0),
            )
        except Exception:
            logger.exception("Could not persist crawler failure for scan_id=%s", scan_id)
        return {
            "status": "failed",
            "failure": failure.to_payload(),
            "scan_id": str(scan_id),
        }


@crawler_celery_app.task(
    bind=True,
    name="privacheck.crawler.worker_probe",
    ignore_result=False,
    shared=False,
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
