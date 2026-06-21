import time

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.observability.logging import get_logger

logger = get_logger("llm-service.rate_limit")


async def rate_limit_middleware(request: Request, call_next):
    settings = get_settings()
    limit = settings.rate_limit_per_min
    if limit <= 0 or request.url.path not in {
        "/chat",
        "/chat/stream",
        "/chat/batch",
        "/features/chat",
        "/features/chat/stream",
    }:
        return await call_next(request)

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return await call_next(request)

    client_key = request.headers.get("x-user-id") or (
        request.client.host if request.client else "unknown"
    )
    bucket = int(time.time()) // 60
    key = f"rate:{client_key}:{bucket}"

    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except Exception as exc:
        logger.warning("rate_limit_redis_error", error=str(exc))
        return await call_next(request)

    if count > limit:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": f"Превышен лимит {limit} запросов в минуту",
                }
            },
            headers={"X-Request-ID": getattr(request.state, "request_id", "")},
        )

    return await call_next(request)
