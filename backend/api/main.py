"""FastAPI API and optional same-origin Render demo frontend."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes.auth import router as auth_router, google_callback
from backend.api.routes.admin import router as admin_router
from backend.api.routes.scans import router as scans_router
from backend.api.routes.frameworks import router as frameworks_router
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
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
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


# Local Compose retains its historical unprefixed endpoints. The hosted demo
# uses /api/* to avoid collisions with React pages /scans and /admin.
SERVE_FRONTEND = os.environ.get("PRIVACHECK_SERVE_FRONTEND", "").lower() in {
    "1", "true", "yes"
}

if SERVE_FRONTEND:
    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(scans_router, prefix="/api")
    app.include_router(frameworks_router, prefix="/api")

    # Google OAuth configuration intentionally keeps the original callback URL
    # /auth/google/callback, separately from the /api/auth/google/start route.
    app.add_api_route(
        "/auth/google/callback", google_callback, methods=["GET"],
        include_in_schema=False,
    )

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend_dist"
    frontend_index = frontend_dist / "index.html"
    if not frontend_index.is_file():
        raise RuntimeError("PRIVACHECK_SERVE_FRONTEND requires built frontend_dist/index.html")
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")


@app.get("/healthz", tags=["Health"], summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "PrivaCheck API"}


if SERVE_FRONTEND:
    @app.get("/", include_in_schema=False)
    def frontend_home() -> FileResponse:
        return FileResponse(frontend_index, headers={"Cache-Control": "no-store"})


    @app.get("/{path:path}", include_in_schema=False)
    def frontend_page(path: str) -> FileResponse:
        # Never return React HTML in response to misspelled API/auth endpoints,
        # or requests for a nonexistent static asset.
        first_segment = path.split("/", 1)[0]
        if first_segment in {"api", "auth", "assets"} or "." in path.split("/")[-1]:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(frontend_index, headers={"Cache-Control": "no-store"})
else:
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(scans_router)
    app.include_router(frameworks_router)

    @app.get("/", include_in_schema=False)
    def legacy_health_check() -> dict[str, str]:
        return health_check()
