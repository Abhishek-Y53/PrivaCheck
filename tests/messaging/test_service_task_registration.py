from backend.infrastructure.messaging.celery_app import (
    COMPLIANCE_QUEUE,
    CRAWLER_QUEUE,
    celery_app,
)
from backend.services.compliance_service.tasks import (
    COMPLIANCE_EVALUATION_TASK,
    compliance_worker_probe,
    evaluate_compliance_scan,
)
from backend.services.crawler_service.tasks import (
    COMPLIANCE_EVALUATION_TASK as CRAWLER_COMPLIANCE_TASK,
    crawler_worker_probe,
    execute_crawler_scan,
)


def test_real_service_tasks_are_registered_with_expected_names() -> None:
    assert execute_crawler_scan.name == "privacheck.crawler.execute_scan"
    assert crawler_worker_probe.name == "privacheck.crawler.worker_probe"
    assert evaluate_compliance_scan.name == "privacheck.compliance.evaluate_scan"
    assert compliance_worker_probe.name == "privacheck.compliance.worker_probe"
    assert COMPLIANCE_EVALUATION_TASK == CRAWLER_COMPLIANCE_TASK


def test_task_routes_assign_workers_to_independent_queues() -> None:
    routes = celery_app.conf.task_routes
    assert routes["privacheck.crawler.*"]["queue"] == CRAWLER_QUEUE
    assert routes["privacheck.compliance.*"]["queue"] == COMPLIANCE_QUEUE
    assert CRAWLER_QUEUE != COMPLIANCE_QUEUE


def test_both_service_queues_are_declared() -> None:
    queue_names = {queue.name for queue in celery_app.conf.task_queues}
    assert CRAWLER_QUEUE in queue_names
    assert COMPLIANCE_QUEUE in queue_names
