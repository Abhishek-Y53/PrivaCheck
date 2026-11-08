"""Factory for independently registered Celery service applications."""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from backend.core.config import settings


def create_worker_app(
    *,
    app_name: str,
    queue_name: str,
    task_namespace: str,
    include_module: str,
) -> Celery:
    """Create a service-specific Celery app that registers one task module."""
    app = Celery(
        app_name,
        broker=settings.BROKER_URL,
        backend=settings.BROKER_URL,
        include=[include_module],
    )
    app.conf.update(
        accept_content=["json"],
        task_serializer="json",
        result_serializer="json",
        enable_utc=True,
        timezone="UTC",
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        task_default_queue=queue_name,
        task_default_exchange=queue_name,
        task_default_routing_key=queue_name,
        task_queues=(Queue(queue_name, routing_key=queue_name),),
        task_routes={f"{task_namespace}.*": {"queue": queue_name}},
        task_create_missing_queues=False,
    )
    return app
