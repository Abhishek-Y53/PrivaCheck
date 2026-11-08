"""Celery tasks for the independently deployed compliance service."""

from __future__ import annotations

import logging
from typing import Any

from celery.exceptions import Retry
from sqlalchemy.exc import InterfaceError, OperationalError

from backend.contracts.task_messages import (
    ComplianceEvaluationCompleted,
    ComplianceEvaluationFailed,
    ComplianceEvaluationRequested,
    parse_task_message,
)
from backend.services.compliance_service.celery_app import compliance_celery_app
from backend.services.compliance_service.evaluation_service import (
    ComplianceEvaluationService,
    EvaluationRejected,
)

logger = logging.getLogger(__name__)

COMPLIANCE_EVALUATION_TASK = "privacheck.compliance.evaluate_scan"


def _failure_payload(
    scan_id: object,
    failure_code: str,
    *,
    retryable: bool = False,
) -> dict[str, object]:
    failure = ComplianceEvaluationFailed(
        scan_id=scan_id,
        failure_code=failure_code,
        retryable=retryable,
    )
    return {
        "status": "failed",
        "service": "compliance",
        "failure": failure.to_payload(),
    }


def _retry_database_failure(
    task: Any,
    service: ComplianceEvaluationService,
    message: ComplianceEvaluationRequested,
    error: Exception,
) -> dict[str, object]:
    """Retry transient PostgreSQL connectivity errors with bounded backoff."""
    retries = int(task.request.retries or 0)
    if retries < int(task.max_retries):
        countdown = min(5 * (2 ** retries), 30)
        raise task.retry(exc=error, countdown=countdown)

    # Only write a terminal failure after the retry budget is exhausted.
    # If PostgreSQL is still unavailable, let the task fail visibly rather than
    # claim that the scan was marked FAILED when it was not.
    service.mark_failed(message.scan_id, "COMPLIANCE_INTERNAL_ERROR")
    logger.exception(
        "Compliance database retries exhausted for scan_id=%s",
        message.scan_id,
        exc_info=(type(error), error, error.__traceback__),
    )
    return _failure_payload(
        message.scan_id,
        "COMPLIANCE_INTERNAL_ERROR",
        retryable=False,
    )


@compliance_celery_app.task(
    bind=True,
    name=COMPLIANCE_EVALUATION_TASK,
    ignore_result=False,
    shared=False,
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
    default_retry_delay=5,
)
def evaluate_compliance_scan(
    self: Any,
    payload: dict[str, object],
) -> dict[str, object]:
    """Evaluate staged observations and atomically persist the final report."""
    message = parse_task_message(payload)
    if not isinstance(message, ComplianceEvaluationRequested):
        raise ValueError("Compliance worker received an unsupported message type.")

    service = ComplianceEvaluationService()
    try:
        outcome = service.evaluate(message)
    except EvaluationRejected as exc:
        try:
            service.mark_failed(message.scan_id, exc.failure_code)
        except (OperationalError, InterfaceError) as db_error:
            return _retry_database_failure(self, service, message, db_error)
        logger.warning(
            "Compliance evaluation rejected for scan_id=%s failure_code=%s",
            message.scan_id,
            exc.failure_code,
        )
        return _failure_payload(message.scan_id, exc.failure_code)
    except (OperationalError, InterfaceError) as exc:
        return _retry_database_failure(self, service, message, exc)
    except Retry:
        raise
    except Exception:
        logger.exception("Unexpected compliance evaluation failure for scan_id=%s", message.scan_id)
        try:
            service.mark_failed(message.scan_id, "EVALUATION_FAILED")
        except (OperationalError, InterfaceError) as db_error:
            return _retry_database_failure(self, service, message, db_error)
        return _failure_payload(message.scan_id, "EVALUATION_FAILED")

    if outcome.status == "skipped":
        return {
            "status": "skipped",
            "service": "compliance",
            "scan_id": outcome.scan_id,
            "reason": outcome.reason or "already_terminal",
            "worker": str(self.request.hostname or "unknown"),
        }

    completion = ComplianceEvaluationCompleted(
        scan_id=message.scan_id,
        result_count=outcome.result_count,
        compliance_status=outcome.compliance_status or "MANUAL_REVIEW",
        risk_score=float(outcome.risk_score or 0.0),
    )
    return {
        "status": "completed",
        "service": "compliance",
        "scan_id": outcome.scan_id,
        "result_count": outcome.result_count,
        "compliance_status": outcome.compliance_status,
        "risk_score": outcome.risk_score,
        "completion_event": completion.to_payload(),
        "task_id": str(self.request.id),
        "worker": str(self.request.hostname or "unknown"),
    }


@compliance_celery_app.task(
    bind=True,
    name="privacheck.compliance.worker_probe",
    ignore_result=False,
    shared=False,
)
def compliance_worker_probe(
    self: Any,
    payload: dict[str, object],
) -> dict[str, str | int]:
    """Retain a lightweight queue diagnostic that does not evaluate scans."""
    message = parse_task_message(payload)
    if not isinstance(message, ComplianceEvaluationRequested):
        raise ValueError("Compliance worker received an unsupported message type.")
    return {
        "status": "ok",
        "service": "compliance",
        "schema_version": message.schema_version,
        "message_id": str(message.message_id),
        "scan_id": str(message.scan_id),
        "framework_id": message.framework_id,
        "task_id": str(self.request.id),
        "worker": str(self.request.hostname or "unknown"),
    }
