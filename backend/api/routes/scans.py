from fastapi import APIRouter, HTTPException

from backend.api.schemas import ScanRequest, ScanResponse
from backend.api.services.scan_service import ScanService

router = APIRouter(
    prefix="/scans",
    tags=["Scans"],
)

scan_service = ScanService()


@router.post(
    "",
    response_model=ScanResponse,
    summary="Scan a website",
    description=(
        "Run a compliance assessment against a website using "
        "the selected compliance framework."
    ),
)
async def create_scan(request: ScanRequest) -> ScanResponse:
    """
    Start a website compliance scan.
    """
    try:
        result = await scan_service.scan(request)
        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while running the scan.",
        ) from exc