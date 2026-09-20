from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.rate_limit import check_rate_limit, resolve_key_and_limit

settings = get_settings()

app = FastAPI(
    title="eminidatabase Control Plane",
    description="Phase 1 — auth, organizations, projects, RBAC, audit.",
    version="0.1.0",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """cf. app/core/rate_limit.py — docs/architecture/04 §4.6, a confirmed gap
    closed in Phase 11. /health is exempt (infra liveness probes, not public
    API traffic)."""

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        key, limit = await resolve_key_and_limit(request)
        allowed, retry_after = check_rate_limit(key, limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded, try again later"},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)
app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
