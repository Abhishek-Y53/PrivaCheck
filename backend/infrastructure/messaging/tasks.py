"""Small infrastructure task used to verify Valkey-to-worker delivery."""

from __future__ import annotations

from celery import Task

from backend.infrastructure.messaging.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="privacheck.messaging.health_check",
    ignore_result=False,
)
def messaging_health_check(self: Task, nonce: str) -> dict[str, str]:
    """Return a deterministic acknowledgement from a running worker.

    This is an infrastructure smoke-test task, not a crawler or compliance
    task. Real service tasks will be registered under their own namespaces.
    """
    return {
        "status": "ok",
        "nonce": nonce,
        "task_id": str(self.request.id),
        "worker": str(self.request.hostname or "unknown"),
    }
