from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request) -> dict:
    cache = getattr(request.app.state, "redis", None)
    cache_ok = False
    if cache is not None:
        try:
            await cache.ping()
            cache_ok = True
        except Exception:
            cache_ok = False
    return {
        "status": "ready" if cache_ok else "degraded",
        "components": {
            "llm": getattr(request.app.state, "llm", None) is not None,
            "redis": cache_ok,
            "docintel": getattr(request.app.state, "docintel_client", None) is not None,
        },
    }
