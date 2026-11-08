"""FastAPI application entry point with sanitized validation errors and CORS."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes.auth import router as auth_router
from backend.api.routes.scans import router as scans_router
from backend.core.config import settings

app = FastAPI(
    title="PrivaCheck API",
    description=(
        "Configurable web compliance assessment API. "
        "Submit a public website URL and registered compliance framework "
        "to run a technical compliance assessment."
    ),
    version="0.1.0",
)

# Authentication uses HttpOnly cookies. Credentialed CORS is restricted to
# exact configured origins; wildcard origins are rejected by Settings.
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation locations/messages without reflecting supplied values.

    FastAPI's default validation body includes the rejected ``input`` value.
    For scan URLs that value may contain access tokens or other query secrets,
    so this handler intentionally omits ``input`` and exception context.
    """
    safe_errors = []
    for error in exc.errors():
        location = list(error.get("loc", ()))
        last_field = str(location[-1]) if location else "request"
        if last_field in {"website", "url"}:
            message = "Website URL is invalid or unsupported."
        elif last_field == "framework":
            message = "The requested compliance framework is not supported."
        else:
            message = "Request validation failed."

        safe_errors.append(
            {
                "loc": location,
                "msg": message,
                "type": str(error.get("type", "value_error")),
            }
        )

    return JSONResponse(status_code=422, content={"detail": safe_errors})


app.include_router(auth_router)
app.include_router(scans_router)


@app.get("/", tags=["Health"], summary="API health check")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "PrivaCheck API"}
