"""Celery producer/diagnostic application and shared queue topology.

Service workers use their own Celery applications and register only their own
implementation modules. This application is used by the API and other producers
to publish named tasks without importing service internals.
"""

from celery import Celery
from kombu import Queue

from backend.core.config import settings


HEALTH_QUEUE = "privacheck.health"
CRAWLER_QUEUE = "crawler.scan"
COMPLIANCE_QUEUE = "compliance.evaluate"

celery_app = Celery(
    "privacheck-producer",
    broker=settings.BROKER_URL,
    backend=settings.BROKER_URL,
    include=["backend.infrastructure.messaging.tasks"],
)

celery_app.conf.update(
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
    task_default_queue=HEALTH_QUEUE,
    task_default_exchange=HEALTH_QUEUE,
    task_default_routing_key=HEALTH_QUEUE,
    task_queues=(
        Queue(HEALTH_QUEUE, routing_key=HEALTH_QUEUE),
        Queue(CRAWLER_QUEUE, routing_key=CRAWLER_QUEUE),
        Queue(COMPLIANCE_QUEUE, routing_key=COMPLIANCE_QUEUE),
    ),
    task_routes={
        "privacheck.messaging.health_check": {"queue": HEALTH_QUEUE},
        "privacheck.crawler.*": {"queue": CRAWLER_QUEUE},
        "privacheck.compliance.*": {"queue": COMPLIANCE_QUEUE},
    },
    task_create_missing_queues=False,
)
