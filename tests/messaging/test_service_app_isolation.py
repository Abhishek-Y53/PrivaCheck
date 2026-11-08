from backend.services.crawler_service.celery_app import crawler_celery_app
from backend.services.compliance_service.celery_app import compliance_celery_app


def test_crawler_app_registers_only_crawler_service_tasks():
    crawler_celery_app.loader.import_default_modules()

    assert "privacheck.crawler.execute_scan" in crawler_celery_app.tasks
    assert "privacheck.crawler.worker_probe" in crawler_celery_app.tasks
    assert "privacheck.compliance.evaluate_scan" not in crawler_celery_app.tasks
    assert "privacheck.compliance.worker_probe" not in crawler_celery_app.tasks
    assert {queue.name for queue in crawler_celery_app.conf.task_queues} == {"crawler.scan"}


def test_compliance_app_registers_only_compliance_service_tasks():
    compliance_celery_app.loader.import_default_modules()

    assert "privacheck.compliance.evaluate_scan" in compliance_celery_app.tasks
    assert "privacheck.compliance.worker_probe" in compliance_celery_app.tasks
    assert "privacheck.crawler.execute_scan" not in compliance_celery_app.tasks
    assert "privacheck.crawler.worker_probe" not in compliance_celery_app.tasks
    assert {queue.name for queue in compliance_celery_app.conf.task_queues} == {"compliance.evaluate"}
