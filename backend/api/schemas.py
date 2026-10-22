"""Public API request/response models with URL policy validation."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.core import CheckResult, ComplianceStatus
from backend.security.url_validation import MAX_URL_LENGTH, normalize_http_url


class ScanRequest(BaseModel):
    """Input received from API clients.

    This performs strict URL syntax/policy checks without doing DNS. The scan
    pipeline must still asynchronously validate DNS answers before crawling.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    website: str = Field(
        min_length=1,
        max_length=MAX_URL_LENGTH,
        description="Public website URL to assess (HTTP or HTTPS, standard port only)",
        examples=["https://www.example.com/"],
        json_schema_extra={"format": "uri"},
    )
    framework: Literal["gdpr"] = Field(
        default="gdpr",
        description="Registered compliance framework to use",
    )

    @field_validator("website")
    @classmethod
    def validate_website_syntax(cls, value: str) -> str:
        # URLValidationError extends ValueError, which Pydantic converts to a
        # normal 422 request-validation response; no browser or DNS is started.
        return normalize_http_url(value)


class ScanResponse(BaseModel):
    """Backward-compatible response, extended with report metadata."""

    website: str
    framework: str
    status: ComplianceStatus
    total_checks: int
    passed_checks: int
    failed_checks: int
    observation_count: int
    results: list[CheckResult]
    error: str | None = None

    # Additive fields for the ScanReport integration; existing API fields remain.
    scan_id: str | None = None
    risk_score: float | None = Field(default=None, ge=0.0, le=100.0)
    metadata: dict[str, Any] | None = None
