"""Public API request and response models for asynchronous scan workflows."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.core import CheckResult, ComplianceStatus
from backend.security.url_validation import MAX_URL_LENGTH, normalize_http_url


LifecycleStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


class ScanRequest(BaseModel):
    """Input for starting an asynchronous website assessment.

    URL syntax and basic policy are validated here. DNS/public-IP validation
    remains the crawler's responsibility immediately before network access.
    Framework IDs are normalized here and checked against the trusted registry
    by the API service; callers cannot supply filesystem paths.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    website: str = Field(
        min_length=1,
        max_length=MAX_URL_LENGTH,
        description="Public website URL to assess (HTTP or HTTPS, standard port only)",
        examples=["https://www.example.com/"],
        json_schema_extra={"format": "uri"},
    )
    framework: str = Field(
        default="gdpr",
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
        description="ID of a registered compliance framework",
    )

    @field_validator("website")
    @classmethod
    def validate_website_syntax(cls, value: str) -> str:
        return normalize_http_url(value)

    @field_validator("framework", mode="before")
    @classmethod
    def normalize_framework_id(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Framework ID must be a string")
        return value.strip().lower()


class ScanResponse(BaseModel):
    """Legacy synchronous response model retained for compatibility."""

    website: str
    framework: str
    status: ComplianceStatus
    total_checks: int
    passed_checks: int
    failed_checks: int
    observation_count: int
    results: list[CheckResult]
    error: str | None = None
    scan_id: str | None = None
    risk_score: float | None = Field(default=None, ge=0.0, le=100.0)
    metadata: dict[str, Any] | None = None


class ScanAcceptedResponse(BaseModel):
    """Response returned when a crawler task has been accepted for processing."""

    scan_id: UUID
    lifecycle_status: Literal["QUEUED"]
    website: str
    framework: str
    ruleset_version_id: UUID | None = None  # NULL for historical, unversioned scans
    created_at: datetime
    task_id: str
    status_url: str
    report_url: str


class ScanStatusResponse(BaseModel):
    """Execution state and summary for one scan."""

    scan_id: UUID
    website: str
    framework: str
    ruleset_version_id: UUID | None = None  # NULL for historical, unversioned scans
    lifecycle_status: LifecycleStatus
    compliance_status: ComplianceStatus | None = None
    total_checks: int
    passed_checks: int
    failed_checks: int
    observation_count: int
    risk_score: float | None = Field(default=None, ge=0.0, le=100.0)
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ScanListResponse(BaseModel):
    """Offset-paginated scan summaries."""

    items: list[ScanStatusResponse]
    total: int
    limit: int
    offset: int


class ScanReportResponse(BaseModel):
    """Persisted, sanitized compliance report for a completed scan."""

    scan_id: UUID
    website: str
    framework: str
    ruleset_version_id: UUID | None = None  # NULL for historical, unversioned scans
    lifecycle_status: Literal["COMPLETED"]
    compliance_status: ComplianceStatus
    total_checks: int
    passed_checks: int
    failed_checks: int
    observation_count: int
    risk_score: float = Field(ge=0.0, le=100.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    results: list[CheckResult]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
