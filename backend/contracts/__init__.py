"""Versioned message contracts shared by PrivaCheck services."""

from backend.contracts.task_messages import (
    ComplianceEvaluationCompleted,
    ComplianceEvaluationFailed,
    ComplianceEvaluationRequested,
    CrawlerScanCompleted,
    CrawlerScanFailed,
    CrawlerScanRequested,
    TaskMessage,
    parse_task_message,
)

__all__ = [
    "TaskMessage",
    "CrawlerScanRequested",
    "CrawlerScanCompleted",
    "CrawlerScanFailed",
    "ComplianceEvaluationRequested",
    "ComplianceEvaluationCompleted",
    "ComplianceEvaluationFailed",
    "parse_task_message",
]
