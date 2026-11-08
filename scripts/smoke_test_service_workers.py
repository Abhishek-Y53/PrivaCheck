"""Exercise the separately routed crawler and compliance Celery workers.

Start both workers in separate terminals before running this script:
  python -m celery -A backend.infrastructure.messaging.celery_app:celery_app worker --loglevel=INFO --pool=solo --queues=crawler.scan --hostname=crawler@%h
  python -m celery -A backend.infrastructure.messaging.celery_app:celery_app worker --loglevel=INFO --pool=solo --queues=compliance.evaluate --hostname=compliance@%h

Then run:
  python -m scripts.smoke_test_service_workers
"""

from __future__ import annotations

from uuid import uuid4

from backend.contracts.task_messages import (
    ComplianceEvaluationRequested,
    CrawlerScanRequested,
)
# Importing task objects ensures they are registered in this producer process.
from backend.services.compliance_service.tasks import compliance_worker_probe
from backend.services.crawler_service.tasks import crawler_worker_probe


def main() -> None:
    scan_id = uuid4()
    crawler_message = CrawlerScanRequested(
        scan_id=scan_id,
        target_url="https://example.com/",
    )
    compliance_message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="gdpr",
        observation_count=1,
    )

    # Deliberately omit queue= here: task_routes must route each namespace.
    crawler_result = crawler_worker_probe.apply_async(
        args=[crawler_message.to_payload()]
    )
    compliance_result = compliance_worker_probe.apply_async(
        args=[compliance_message.to_payload()]
    )

    crawler_ack = crawler_result.get(timeout=45, propagate=True)
    compliance_ack = compliance_result.get(timeout=45, propagate=True)

    assert crawler_ack["status"] == "ok"
    assert crawler_ack["service"] == "crawler"
    assert crawler_ack["scan_id"] == str(scan_id)

    assert compliance_ack["status"] == "ok"
    assert compliance_ack["service"] == "compliance"
    assert compliance_ack["scan_id"] == str(scan_id)

    assert crawler_ack["worker"] != compliance_ack["worker"], (
        "Crawler and compliance probes were handled by the same worker. "
        "Start two distinct worker processes with their respective -Q queues."
    )

    print("Independent service-worker routing smoke test passed.")
    print(f"Shared scan ID: {scan_id}")
    print(f"Crawler worker: {crawler_ack['worker']}")
    print(f"Compliance worker: {compliance_ack['worker']}")
    print(f"Crawler task ID: {crawler_ack['task_id']}")
    print(f"Compliance task ID: {compliance_ack['task_id']}")
    print("Each worker consumed only its own queue.")


if __name__ == "__main__":
    main()
