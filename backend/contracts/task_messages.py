"""Versioned, JSON-safe contracts for asynchronous PrivaCheck service messages.

Messages contain identifiers and small control metadata only. Raw browser
observations and compliance evidence must not be put on the broker; workers
retrieve staged observations from the controlled persistence layer by scan_id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Mapping, TypeAlias, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from backend.security.url_validation import normalize_http_url


class TaskMessage(BaseModel):
    """Common envelope shared by all inter-service messages.

    Version 1 is deliberately explicit. Breaking contract changes must use a
    new version rather than silently changing the meaning of existing fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    message_id: UUID = Field(default_factory=uuid4)
    scan_id: UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("occurred_at")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(timezone.utc)

    def to_payload(self) -> dict[str, object]:
        """Return JSON-compatible primitives suitable for Celery's JSON codec."""
        return self.model_dump(mode="json")


class CrawlerScanRequested(TaskMessage):
    message_type: Literal["crawler.scan.requested"] = "crawler.scan.requested"
    target_url: str = Field(min_length=1, max_length=2048)
    timeout_seconds: int = Field(default=180, ge=1, le=300)

    @field_validator("target_url")
    @classmethod
    def validate_target_url(cls, value: str) -> str:
        # Syntax/policy normalization only. The crawler MUST still perform
        # asynchronous DNS/public-IP validation immediately before navigation.
        return normalize_http_url(value)


class CrawlerScanCompleted(TaskMessage):
    message_type: Literal["crawler.scan.completed"] = "crawler.scan.completed"
    observation_count: int = Field(ge=0)


class CrawlerScanFailed(TaskMessage):
    message_type: Literal["crawler.scan.failed"] = "crawler.scan.failed"
    failure_code: Literal[
        "TARGET_REJECTED",
        "CRAWLER_TIMEOUT",
        "BROWSER_START_FAILED",
        "NAVIGATION_FAILED",
        "CRAWLER_INTERNAL_ERROR",
    ]
    retryable: bool = False


class ComplianceEvaluationRequested(TaskMessage):
    message_type: Literal["compliance.evaluation.requested"] = (
        "compliance.evaluation.requested"
    )
    framework_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    observation_count: int = Field(ge=0)
    # Additive field for old queued messages; every new governed scan sets it.
    ruleset_version_id: UUID | None = None


class ComplianceEvaluationCompleted(TaskMessage):
    message_type: Literal["compliance.evaluation.completed"] = (
        "compliance.evaluation.completed"
    )
    result_count: int = Field(ge=0)
    compliance_status: Literal[
        "PASS", "FAIL", "WARNING", "MANUAL_REVIEW", "NOT_APPLICABLE"
    ]
    risk_score: float = Field(ge=0.0, le=100.0)


class ComplianceEvaluationFailed(TaskMessage):
    message_type: Literal["compliance.evaluation.failed"] = (
        "compliance.evaluation.failed"
    )
    failure_code: Literal[
        "UNSUPPORTED_FRAMEWORK",
        "RULE_LOAD_FAILED",
        "OBSERVATIONS_UNAVAILABLE",
        "EVALUATION_FAILED",
        "COMPLIANCE_INTERNAL_ERROR",
    ]
    retryable: bool = False


TaskMessageUnion: TypeAlias = Annotated[
    Union[
        CrawlerScanRequested,
        CrawlerScanCompleted,
        CrawlerScanFailed,
        ComplianceEvaluationRequested,
        ComplianceEvaluationCompleted,
        ComplianceEvaluationFailed,
    ],
    Field(discriminator="message_type"),
]

_TASK_MESSAGE_ADAPTER = TypeAdapter(TaskMessageUnion)


def parse_task_message(payload: Mapping[str, object]) -> TaskMessageUnion:
    """Validate an incoming broker payload and reject unknown contracts."""
    return _TASK_MESSAGE_ADAPTER.validate_python(dict(payload))
