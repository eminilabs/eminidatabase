from fastapi import FastAPI

from mf_app.api.v1.router import api_router
from mf_app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="eminidatabase Microfinance",
    description=(
        "Microfinance business application built on top of the eminidatabase "
        "Cloud Database Platform (Phase 9.1 — onboarding, staff auth/RBAC)."
    ),
    version="0.1.0",
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
