"""End-to-end Celery/Valkey smoke test.

Start a worker in a second terminal before running this script:
    python -m celery -A backend.infrastructure.messaging.celery_app:celery_app \\
        worker --loglevel=INFO --pool=solo --queues=privacheck.health

The solo pool is only for a local Windows development smoke test. Deployment
workers will run in Linux containers and can use the prefork pool.
"""

from __future__ import annotations

from uuid import uuid4

from backend.infrastructure.messaging.celery_app import HEALTH_QUEUE
from backend.infrastructure.messaging.tasks import messaging_health_check


def main() -> None:
    nonce = str(uuid4())
    result = messaging_health_check.apply_async(
        kwargs={"nonce": nonce},
        queue=HEALTH_QUEUE,
    )

    payload = result.get(timeout=30, propagate=True)
    if not isinstance(payload, dict):
        raise RuntimeError("Worker returned an unexpected result type")
    if payload.get("status") != "ok" or payload.get("nonce") != nonce:
        raise RuntimeError("Worker acknowledgement did not match the submitted task")
    if payload.get("task_id") != result.id:
        raise RuntimeError("Worker task ID did not match the producer task ID")

    print("Celery/Valkey messaging smoke test passed.")
    print(f"Task ID: {result.id}")
    print(f"Worker: {payload.get('worker')}")
    print(f"Queue: {HEALTH_QUEUE}")


if __name__ == "__main__":
    main()
