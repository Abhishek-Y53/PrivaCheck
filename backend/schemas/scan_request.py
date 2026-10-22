"""Validated request models for scan-facing API endpoints."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.security.url_validation import MAX_URL_LENGTH, normalize_http_url


class ScanRequest(BaseModel):
    """Input contract for starting a scan.

    This performs fast syntactic/policy validation only. The scan service must
    still call ``await validate_public_http_url(request.url)`` immediately
    before creating network activity to check DNS answers.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)

    @field_validator("url")
    @classmethod
    def validate_url_syntax(cls, value: str) -> str:
        return normalize_http_url(value)
