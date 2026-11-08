"""Authenticated, owner-scoped scan submission, status, report, and listing."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.api.dependencies.auth import get_current_user, require_csrf
from backend.api.schemas import (
    ScanAcceptedResponse,
    ScanListResponse,
    ScanReportResponse,
    ScanRequest,
    ScanStatusResponse,
)
from backend.api.services.async_scan_service import (
    AsyncScanService,
    ScanEnqueueError,
    ScanNotFoundError,
    ScanReportNotReadyError,
    ScanServiceUnavailableError,
    UnsupportedFrameworkError,
)
from backend.infrastructure.database.models.user import User

router = APIRouter(prefix="/scans", tags=["Scans"])
scan_service = AsyncScanService()

LifecycleFilter = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


def _mark_private(response: Response) -> None:
    """Prevent browsers and intermediary caches from storing user scan data."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "",
    response_model=ScanAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an asynchronous website scan",
    description=(
        "Creates a scan owned by the authenticated account and submits a crawler "
        "task. The response is returned immediately; retrieve execution status "
        "and the final report using the URLs in the response."
    ),
)
async def create_scan(
    request: ScanRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_csrf),
) -> ScanAcceptedResponse:
    _mark_private(response)
    try:
        return await scan_service.submit_scan(request, user_id=current_user.id)
    except UnsupportedFrameworkError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScanEnqueueError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "The scan could not be submitted to the processing queue.",
                "scan_id": str(exc.scan_id),
            },
        ) from None
    except ScanServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="The scan service is temporarily unavailable.",
        ) from None


@router.get(
    "",
    response_model=ScanListResponse,
    summary="List scans owned by the authenticated account",
)
async def list_scans(
    response: Response,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    lifecycle_status: LifecycleFilter | None = Query(default=None),
) -> ScanListResponse:
    _mark_private(response)
    try:
        return await scan_service.list_scans(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            lifecycle_status=lifecycle_status,
        )
    except ScanServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="The scan service is temporarily unavailable.",
        ) from None


@router.get(
    "/{scan_id}",
    response_model=ScanStatusResponse,
    summary="Get status for an owned scan",
)
async def get_scan_status(
    scan_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> ScanStatusResponse:
    _mark_private(response)
    try:
        return await scan_service.get_scan_status(scan_id, user_id=current_user.id)
    except ScanNotFoundError:
        # Same response for nonexistent and foreign-owned IDs.
        raise HTTPException(status_code=404, detail="Scan not found.") from None
    except ScanServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="The scan service is temporarily unavailable.",
        ) from None


@router.get(
    "/{scan_id}/report",
    response_model=ScanReportResponse,
    summary="Get the final report for an owned scan",
)
async def get_scan_report(
    scan_id: UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> ScanReportResponse:
    _mark_private(response)
    try:
        return await scan_service.get_scan_report(scan_id, user_id=current_user.id)
    except ScanNotFoundError:
        raise HTTPException(status_code=404, detail="Scan not found.") from None
    except ScanReportNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The final report is not available.",
                "lifecycle_status": exc.lifecycle_status,
                "error": exc.error,
            },
        ) from None
    except ScanServiceUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="The scan service is temporarily unavailable.",
        ) from None
