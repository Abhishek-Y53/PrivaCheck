"""Celery application for the independently deployable compliance service."""

from backend.infrastructure.messaging.worker_app import create_worker_app


COMPLIANCE_QUEUE = "compliance.evaluate"

compliance_celery_app = create_worker_app(
    app_name="privacheck-compliance",
    queue_name=COMPLIANCE_QUEUE,
    task_namespace="privacheck.compliance",
    include_module="backend.services.compliance_service.tasks",
)
