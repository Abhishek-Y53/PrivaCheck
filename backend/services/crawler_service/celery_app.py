"""Celery application for the independently deployable crawler service."""

from backend.infrastructure.messaging.worker_app import create_worker_app


CRAWLER_QUEUE = "crawler.scan"

crawler_celery_app = create_worker_app(
    app_name="privacheck-crawler",
    queue_name=CRAWLER_QUEUE,
    task_namespace="privacheck.crawler",
    include_module="backend.services.crawler_service.tasks",
)
