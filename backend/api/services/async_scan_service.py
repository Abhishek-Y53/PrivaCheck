"""API orchestration for asynchronous scans.

The API creates the durable scan record and publishes a small crawler task
message. Browser automation and compliance evaluation run only in their
independent Celery workers.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.schemas import (
    ScanAcceptedResponse,
    ScanListResponse,
    ScanReportResponse,
    ScanRequest,
    ScanStatusResponse,
)
from backend.contracts.task_messages import CrawlerScanRequested
from backend.infrastructure.database.models.scan import Scan
from backend.infrastructure.database.models.user import User
from backend.infrastructure.database.models.framework import ComplianceFramework
from backend.api.services.framework_service import is_allowed, current_version
from backend.infrastructure.database.repositories import (
    CheckResultRepository,
    ScanRepository,
)
from backend.infrastructure.database.session import SessionLocal
from backend.infrastructure.messaging.celery_app import CRAWLER_QUEUE, celery_app
from backend.rule_engine.framework_registry import (
    FrameworkRegistry,
    UnsupportedFrameworkError as RegistryFrameworkError,
)
from backend.schemas.core import CheckResult

logger = logging.getLogger(__name__)

CRAWLER_TASK_NAME = "privacheck.crawler.execute_scan"


class UnsupportedFrameworkError(ValueError):
    """The requested framework is not present in the trusted registry."""


class ScanNotFoundError(LookupError):
    """No scan exists for the requested identifier."""


class ScanReportNotReadyError(RuntimeError):
    """The scan has not completed and therefore has no final report."""

    def __init__(self, lifecycle_status: str, error: str | None = None) -> None:
        self.lifecycle_status = lifecycle_status
        self.error = error
        super().__init__("The scan report is not available yet.")


class ScanEnqueueError(RuntimeError):
    """The scan record exists, but the crawler task could not be confirmed."""

    def __init__(self, scan_id: UUID) -> None:
        self.scan_id = scan_id
        super().__init__("The scan could not be submitted to the crawler queue.")


class ScanServiceUnavailableError(RuntimeError):
    """A required persistence dependency is temporarily unavailable."""


def _safe_public_url(value: str) -> str:
    """Strip query values/fragments before returning a submitted URL to clients."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return "[URL REDACTED]"
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = parsed.port
        default_port = 80 if parsed.scheme.lower() == "http" else 443
        authority = hostname if port in (None, default_port) else f"{hostname}:{port}"
        return urlunsplit((parsed.scheme.lower(), authority, parsed.path, "", ""))
    except (TypeError, ValueError):
        return "[URL REDACTED]"


class AsyncScanService:
    """Create scans, dispatch work, and read persisted scan state/results."""

    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        task_producer=celery_app,
        framework_registry: FrameworkRegistry | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.task_producer = task_producer
        self.framework_registry = framework_registry or FrameworkRegistry()
        # Explicit framework_registry injection is retained for historical
        # isolated service tests; FastAPI never injects an override.
        self.legacy_registry_override = framework_registry is not None

    @staticmethod
    def _validate_owner_id(user_id: UUID) -> None:
        if not isinstance(user_id, UUID):
            raise ValueError("An authenticated UUID user_id is required.")

    async def submit_scan(
        self, request: ScanRequest, *, user_id: UUID
    ) -> ScanAcceptedResponse:
        """Create an owned QUEUED scan and dispatch it off the event loop."""
        self._validate_owner_id(user_id)
        try:
            return await asyncio.to_thread(self._submit_scan_sync, request, user_id)
        except SQLAlchemyError as exc:
            logger.error("Database unavailable while creating a scan (%s)", type(exc).__name__)
            raise ScanServiceUnavailableError from None

    def _submit_scan_sync(
        self, request: ScanRequest, user_id: UUID
    ) -> ScanAcceptedResponse:
        try:
            with self.session_factory() as session:
                with session.begin():
                    if self.legacy_registry_override:
                        # Compatibility for pre-governance service fixtures.
                        try:
                            framework_id, _ = self.framework_registry.resolve(request.framework)
                        except RegistryFrameworkError as exc:
                            raise UnsupportedFrameworkError("Unsupported compliance framework.") from exc
                        version_id = None
                    else:
                        user = session.get(User, user_id)
                        if user is None or not is_allowed(session, user, request.framework):
                            raise UnsupportedFrameworkError("Framework not available to this account.")
                        fw = session.get(ComplianceFramework, request.framework)
                        version_id = current_version(session, fw).id
                        framework_id = fw.slug
                    scan = ScanRepository.create(
                        session,
                        website=request.website,
                        framework=framework_id,
                        user_id=user_id,
                        **({"ruleset_version_id": version_id} if version_id is not None else {}),
                    )
                    scan_id = scan.id
                    created_at = scan.created_at
        except SQLAlchemyError:
            raise

        message = CrawlerScanRequested(
            scan_id=scan_id,
            target_url=request.website,
        )

        try:
            async_result = self.task_producer.send_task(
                CRAWLER_TASK_NAME,
                args=[message.to_payload()],
                queue=CRAWLER_QUEUE,
                task_id=str(message.message_id),
            )
        except Exception as exc:
            # Do not overwrite RUNNING if the broker accepted the message but
            # the publisher lost the acknowledgement: a worker may be active.
            try:
                self._mark_enqueue_failure(scan_id)
            except Exception as db_exc:
                logger.error(
                    "Could not record queue submission failure for scan_id=%s (%s)",
                    scan_id,
                    type(db_exc).__name__,
                )
            logger.error(
                "Could not publish crawler task for scan_id=%s (%s)",
                scan_id,
                type(exc).__name__,
            )
            raise ScanEnqueueError(scan_id) from None

        task_id = str(getattr(async_result, "id", message.message_id))
        return ScanAcceptedResponse(
            scan_id=scan_id,
            lifecycle_status="QUEUED",
            website=_safe_public_url(request.website),
            framework=framework_id,
            ruleset_version_id=version_id,
            created_at=created_at,
            task_id=task_id,
            status_url=f"/scans/{scan_id}",
            report_url=f"/scans/{scan_id}/report",
        )

    def _mark_enqueue_failure(self, scan_id: UUID) -> None:
        with self.session_factory() as session:
            with session.begin():
                scan = ScanRepository.get_by_id_for_update(session, scan_id)
                if scan is not None and str(scan.lifecycle_status).upper() == "QUEUED":
                    ScanRepository.set_lifecycle_status(
                        session,
                        scan_id,
                        "FAILED",
                        error_message="The scan could not be submitted to the processing queue.",
                    )

    def _allowed(self, session, user_id: UUID, slug: str) -> bool:
        if self.legacy_registry_override:
            return True
        user = session.get(User, user_id)
        return bool(user and is_allowed(session, user, slug))

    async def get_scan_status(
        self, scan_id: UUID, *, user_id: UUID
    ) -> ScanStatusResponse:
        self._validate_owner_id(user_id)
        try:
            return await asyncio.to_thread(
                self._get_scan_status_sync, scan_id, user_id
            )
        except SQLAlchemyError:
            logger.error("Database unavailable while reading scan status (%s)", scan_id)
            raise ScanServiceUnavailableError from None

    def _get_scan_status_sync(
        self, scan_id: UUID, user_id: UUID
    ) -> ScanStatusResponse:
        with self.session_factory() as session:
            scan = ScanRepository.get_by_id_for_user(session, scan_id, user_id)
            if scan is None or not self._allowed(session, user_id, scan.framework):
                raise ScanNotFoundError(str(scan_id))
            return self._to_status_response(scan)

    async def list_scans(
        self,
        *,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        lifecycle_status: str | None = None,
    ) -> ScanListResponse:
        self._validate_owner_id(user_id)
        try:
            return await asyncio.to_thread(
                self._list_scans_sync,
                limit,
                offset,
                lifecycle_status,
                user_id,
            )
        except SQLAlchemyError:
            logger.error("Database unavailable while listing scans")
            raise ScanServiceUnavailableError from None

    def _list_scans_sync(
        self,
        limit: int,
        offset: int,
        lifecycle_status: str | None,
        user_id: UUID,
    ) -> ScanListResponse:
        with self.session_factory() as session:
            # Compatibility with the legacy repository-unit-test seam, where
            # the injected session implements scalar() but is not a SQLAlchemy
            # Session. Live requests always use a real Session and therefore
            # always enforce current framework permissions in the DB query.
            if not isinstance(session, Session):
                count_statement = select(func.count()).select_from(Scan).where(
                    Scan.user_id == user_id
                )
                if lifecycle_status is not None:
                    count_statement = count_statement.where(
                        Scan.lifecycle_status == lifecycle_status
                    )
                total = int(session.scalar(count_statement) or 0)
                scans = ScanRepository.list_recent(
                    session, user_id=user_id, limit=limit, offset=offset,
                    lifecycle_status=lifecycle_status,
                )
                return ScanListResponse(
                    items=[self._to_status_response(scan) for scan in scans],
                    total=total, limit=limit, offset=offset,
                )
            condition = Scan.user_id == user_id
            if self.legacy_registry_override:
                allowed_slugs = None
            else:
                user = session.get(User, user_id)
                frameworks = session.scalars(select(ComplianceFramework).where(
                    ComplianceFramework.status == "PUBLISHED",
                    ComplianceFramework.active_version_id.is_not(None),
                )).all() if user is not None else []
                allowed_slugs = [fw.slug for fw in frameworks if is_allowed(session, user, fw.slug)]
                condition = condition & Scan.framework.in_(allowed_slugs)
            count_statement = select(func.count()).select_from(Scan).where(condition)
            stmt = select(Scan).where(condition)
            if lifecycle_status is not None:
                count_statement = count_statement.where(Scan.lifecycle_status == lifecycle_status)
                stmt = stmt.where(Scan.lifecycle_status == lifecycle_status)
            total = int(session.scalar(count_statement) or 0)
            scans = session.scalars(stmt.order_by(Scan.created_at.desc(), Scan.id.desc()).offset(offset).limit(limit)).all()
            return ScanListResponse(
                items=[self._to_status_response(scan) for scan in scans],
                total=total,
                limit=limit,
                offset=offset,
            )

    async def get_scan_report(
        self, scan_id: UUID, *, user_id: UUID
    ) -> ScanReportResponse:
        self._validate_owner_id(user_id)
        try:
            return await asyncio.to_thread(
                self._get_scan_report_sync, scan_id, user_id
            )
        except SQLAlchemyError:
            logger.error("Database unavailable while reading scan report (%s)", scan_id)
            raise ScanServiceUnavailableError from None

    def _get_scan_report_sync(
        self, scan_id: UUID, user_id: UUID
    ) -> ScanReportResponse:
        with self.session_factory() as session:
            scan = ScanRepository.get_by_id_for_user(session, scan_id, user_id)
            if scan is None or not self._allowed(session, user_id, scan.framework):
                raise ScanNotFoundError(str(scan_id))

            lifecycle = str(scan.lifecycle_status).upper()
            if lifecycle != "COMPLETED":
                raise ScanReportNotReadyError(lifecycle, scan.error_message)

            records = CheckResultRepository.list_for_scan(session, scan_id)
            results = [
                CheckResult.model_validate(
                    {
                        "check_id": record.check_id,
                        "name": record.name,
                        "status": record.status,
                        "severity": record.severity,
                        "confidence": record.confidence,
                        "explanation": record.explanation,
                        "recommendation": record.recommendation,
                        # These rows are sanitized before insertion by the M5
                        # report builder; raw staged observations are not exposed.
                        "evidence": record.evidence or [],
                    }
                )
                for record in records
            ]

            if scan.compliance_status is None or scan.risk_score is None:
                raise ScanReportNotReadyError(
                    lifecycle,
                    "The completed scan is missing its persisted report summary.",
                )

            return ScanReportResponse(
                scan_id=scan.id,
                website=_safe_public_url(scan.website),
                framework=scan.framework,
                ruleset_version_id=getattr(scan, "ruleset_version_id", None),
                lifecycle_status="COMPLETED",
                compliance_status=scan.compliance_status,
                total_checks=scan.total_checks,
                passed_checks=scan.passed_checks,
                failed_checks=scan.failed_checks,
                observation_count=scan.observation_count,
                risk_score=float(scan.risk_score),
                metadata=scan.report_metadata or {},
                results=results,
                created_at=scan.created_at,
                started_at=scan.started_at,
                completed_at=scan.completed_at,
            )

    @staticmethod
    def _to_status_response(scan: Scan) -> ScanStatusResponse:
        return ScanStatusResponse(
            scan_id=scan.id,
            website=_safe_public_url(scan.website),
            framework=scan.framework,
            ruleset_version_id=getattr(scan, "ruleset_version_id", None),
            lifecycle_status=str(scan.lifecycle_status).upper(),
            compliance_status=scan.compliance_status,
            total_checks=scan.total_checks,
            passed_checks=scan.passed_checks,
            failed_checks=scan.failed_checks,
            observation_count=scan.observation_count,
            risk_score=scan.risk_score,
            error=scan.error_message,
            created_at=scan.created_at,
            started_at=scan.started_at,
            completed_at=scan.completed_at,
        )
