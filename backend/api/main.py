from fastapi import FastAPI

from backend.api.routes.scans import router as scans_router

app = FastAPI(
    title="PrivaCheck API",
    description=(
        "Configurable web compliance assessment API. "
        "Submit a website URL and compliance framework to run "
        "a technical compliance assessment."
    ),
    version="0.1.0",
)

app.include_router(scans_router)


@app.get(
    "/",
    tags=["Health"],
    summary="API health check",
)
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "PrivaCheck API",
    }