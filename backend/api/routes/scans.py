"""Secure scan API endpoint."""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.schemas import ScanRequest, ScanResponse
from backend.api.services.scan_pipeline import (
    ScanPipelineError,
    ScanTimeoutError,
    UnsafeScanTargetError,
    UnsupportedFrameworkError,
)
from backend.api.services.scan_service import ScanService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scans", tags=["Scans"])
scan_service = ScanService()


@router.post(
    "",
    response_model=ScanResponse,
    summary="Scan a website",
    description=(
        "Run a technical compliance assessment against a public website "
        "using a registered compliance framework."
    ),
)
async def create_scan(request: ScanRequest) -> ScanResponse:
    """Validate the request and return a sanitized assessment report."""
    try:
        return await scan_service.scan(request)
    except (UnsafeScanTargetError, UnsupportedFrameworkError) as exc:
        # Message is a controlled policy message, not an underlying resolver error.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScanTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="The scan exceeded its allowed execution time.",
        ) from exc
    except ScanPipelineError as exc:
        logger.warning("Scan pipeline rejected request: %s", type(exc).__name__)
        raise HTTPException(
            status_code=422,
            detail="The scan request could not be processed.",
        ) from exc
    except Exception:
        # Keep full diagnostics in controlled server logs; never return traceback,
        # filesystem paths, exception strings or secrets to an API caller.
        logger.exception("Unexpected error while processing a scan request")
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while running the scan.",
        ) from None
