import logging
import time
import uuid

import structlog
from fastapi import Request
from structlog.contextvars import bind_contextvars, clear_contextvars


def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str = "llm-service"):
    return structlog.get_logger(name)


async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    user_id = request.headers.get("x-user-id")

    request.state.request_id = request_id
    request.state.llm_cost = 0.0
    request.state.llm_tokens = 0

    bind_contextvars(
        request_id=request_id,
        user_id=user_id,
        path=request.url.path,
        method=request.method,
    )

    log = get_logger()
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled")
        clear_contextvars()
        raise

    duration_ms = (time.perf_counter() - t0) * 1000
    response.headers["x-request-id"] = request_id
    response.headers["X-LLM-Cost-USD"] = f"{request.state.llm_cost:.6f}"
    log.info(
        "request_completed",
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    clear_contextvars()
    return response
