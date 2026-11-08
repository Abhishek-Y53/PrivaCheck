"""Small local smoke test for PrivaCheck service message contracts."""

from uuid import uuid4

from backend.contracts.task_messages import (
    ComplianceEvaluationRequested,
    CrawlerScanRequested,
    parse_task_message,
)


def main() -> None:
    scan_id = uuid4()
    crawler_message = CrawlerScanRequested(
        scan_id=scan_id,
        target_url="https://example.com/",
    )
    crawler_payload = crawler_message.to_payload()
    parsed_crawler = parse_task_message(crawler_payload)
    assert parsed_crawler.scan_id == scan_id

    compliance_message = ComplianceEvaluationRequested(
        scan_id=scan_id,
        framework_id="gdpr",
        observation_count=150,
    )
    compliance_payload = compliance_message.to_payload()
    parsed_compliance = parse_task_message(compliance_payload)
    assert parsed_compliance.scan_id == scan_id

    print("Task-contract smoke test passed.")
    print("Crawler message: validated and JSON serializable")
    print("Compliance message: validated and JSON serializable")
    print(f"Shared scan ID: {scan_id}")


if __name__ == "__main__":
    main()
