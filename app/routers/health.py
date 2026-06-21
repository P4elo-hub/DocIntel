import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

_READY_TIMEOUT_SECONDS = 2.0


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request):
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "redis": "down"},
        )

    try:
        await asyncio.wait_for(redis.ping(), timeout=_READY_TIMEOUT_SECONDS)
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "redis": "down"},
        )

    return {"status": "ok", "redis": "up"}
