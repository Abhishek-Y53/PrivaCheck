"""Compatibility adapter from the secure scan pipeline to the public API model."""

from __future__ import annotations

from typing import Any

from backend.api.schemas import ScanRequest, ScanResponse
from backend.api.services.scan_pipeline import ScanPipelineService


class ScanService:
    """Execute a scan and preserve the existing ScanResponse contract.

    The pipeline owns URL/DNS policy, crawler execution, YAML rule evaluation,
    evidence redaction and report aggregation. This adapter intentionally keeps
    API request/response naming backwards-compatible (``website`` and
    ``results``) while exposing report fields additively.
    """

    def __init__(self, pipeline: ScanPipelineService | None = None) -> None:
        self.pipeline = pipeline or ScanPipelineService()

    async def scan(self, request: ScanRequest) -> ScanResponse:
        report = await self.pipeline.scan(
            url=str(request.website),
            framework=request.framework,
        )

        crawler_status = str(
            report.metadata.get("crawler_status", "UNKNOWN")
        ).upper()
        error = None
        if crawler_status != "COMPLETED":
            # Do not expose crawler exception details or internal addresses.
            error = "The crawler did not complete; findings require manual review."

        return ScanResponse(
            website=report.target_url,
            framework=str(report.metadata.get("framework", request.framework)),
            status=report.overall_status,
            total_checks=report.total_checks,
            passed_checks=report.passed_checks,
            failed_checks=report.failed_checks,
            observation_count=int(report.metadata.get("observation_count", 0)),
            results=report.issues,
            error=error,
            scan_id=report.scan_id,
            risk_score=report.risk_score,
            metadata=report.metadata,
        )
