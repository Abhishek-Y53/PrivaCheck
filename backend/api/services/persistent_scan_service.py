"""Persist results and temporary observations from the synchronous scan pipeline.

This is a transitional M2 integration. The API still waits for the existing
pipeline to finish. The observation sink establishes the temporary artifact
handoff that the independently deployed compliance service will consume later.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from backend.api.schemas import ScanRequest, ScanResponse
from backend.api.services.scan_pipeline import (
    ScanTimeoutError,
    UnsupportedFrameworkError,
    UnsafeScanTargetError,
)
from backend.api.services.scan_service import ScanService
from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ObservationRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.schemas.core import Observation

logger = logging.getLogger(__name__)


class PersistentScanService(ScanService):
    """Run the existing pipeline and persist its sanitized report.

    Raw observations are staged before rule evaluation, then deleted immediately
    after successful evaluation. The 24-hour database TTL is a cleanup backstop
    for interrupted scans, not the normal retention policy.
    """

    def __init__(
        self,
        pipeline: Any | None = None,
        *,
        session_factory=SessionLocal,
    ) -> None:
        super().__init__(pipeline=pipeline)
        self.session_factory = session_factory

    async def scan(self, request: ScanRequest) -> ScanResponse:
        scan_id: UUID | None = None

        try:
            # Persist the request before doing expensive network/browser work.
            with self.session_factory() as session:
                with session.begin():
                    scan = ScanRepository.create(
                        session,
                        website=str(request.website),
                        framework=request.framework,
                    )
                    scan_id = scan.id

            if scan_id is None:
                raise RuntimeError("A scan ID was not generated.")

            # Commit RUNNING before the pipeline starts, so the state is visible
            # to other API requests and remains useful if the process crashes.
            with self.session_factory() as session:
                with session.begin():
                    ScanRepository.set_lifecycle_status(
                        session, scan_id, "RUNNING"
                    )

            async def persist_observations(
                observations: list[Observation],
            ) -> None:
                # SQLAlchemy uses a synchronous session. Run database work in a
                # worker thread rather than blocking FastAPI's event loop.
                await asyncio.to_thread(
                    self._store_observations,
                    scan_id,
                    observations,
                )

            # The pipeline invokes this after collection and before rule
            # evaluation. Raw data is never included in the public API response.
            response = await super().scan(
                request,
                observation_sink=persist_observations,
            )

            if response.risk_score is None:
                raise RuntimeError("The scan pipeline returned no risk score.")

            # The database UUID is the canonical ID exposed to API clients.
            response.scan_id = str(scan_id)

            # Persist sanitized findings and summary atomically, then remove
            # temporary observations after evaluation has completed.
            with self.session_factory() as session:
                with session.begin():
                    CheckResultRepository.replace_for_scan(
                        session, scan_id, response.results
                    )
                    ScanRepository.update_report_summary(
                        session,
                        scan_id,
                        compliance_status=self._enum_value(response.status),
                        total_checks=response.total_checks,
                        passed_checks=response.passed_checks,
                        failed_checks=response.failed_checks,
                        observation_count=response.observation_count,
                        risk_score=float(response.risk_score),
                        report_metadata=response.metadata or {},
                    )
                    ObservationRepository.delete_for_scan(session, scan_id)
                    ScanRepository.set_lifecycle_status(
                        session, scan_id, "COMPLETED"
                    )

            return response

        except Exception as exc:
            if scan_id is not None:
                safe_message = self._safe_failure_message(exc)
                try:
                    with self.session_factory() as session:
                        with session.begin():
                            scan = ScanRepository.get_by_id(session, scan_id)
                            if scan is not None and scan.lifecycle_status in {
                                "QUEUED",
                                "RUNNING",
                            }:
                                ScanRepository.set_lifecycle_status(
                                    session,
                                    scan_id,
                                    "FAILED",
                                    error_message=safe_message,
                                )
                            # Do not retain raw observations from failed scans.
                            ObservationRepository.delete_for_scan(session, scan_id)
                except Exception:
                    # Do not mask the original pipeline or persistence failure.
                    logger.exception(
                        "Could not persist FAILED lifecycle state for scan_id=%s",
                        scan_id,
                    )
            raise

    def _store_observations(
        self,
        scan_id: UUID,
        observations: list[Observation],
    ) -> int:
        """Commit one temporary observation batch for the scan."""
        with self.session_factory() as session:
            with session.begin():
                return ObservationRepository.create_many(
                    session,
                    scan_id,
                    observations,
                )

    @staticmethod
    def _enum_value(value: object) -> str:
        return str(getattr(value, "value", value)).upper()

    @staticmethod
    def _safe_failure_message(exc: Exception) -> str:
        """Return a controlled message; never persist exception text or secrets."""
        if isinstance(exc, UnsafeScanTargetError):
            return "The target URL did not pass scan policy validation."
        if isinstance(exc, UnsupportedFrameworkError):
            return "The requested compliance framework is not supported."
        if isinstance(exc, ScanTimeoutError):
            return "The scan exceeded its allowed execution time."
        return "The scan could not be completed due to an internal error."
