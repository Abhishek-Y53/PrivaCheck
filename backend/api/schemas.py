from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from backend.schemas.core import (
    CheckResult,
    ComplianceStatus,
)


class ScanRequest(BaseModel):
    """
    Input received from Swagger/API clients.
    """

    website: HttpUrl = Field(
        description="Website URL to assess"
    )

    framework: Literal["gdpr"] = Field(
        default="gdpr",
        description="Compliance framework to use"
    )


class ScanResponse(BaseModel):
    """
    Result returned by the compliance scan.
    """

    website: str

    framework: str

    status: ComplianceStatus

    total_checks: int

    passed_checks: int

    failed_checks: int

    observation_count: int

    results: list[CheckResult]

    error: str | None = None