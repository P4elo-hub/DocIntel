import asyncio
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from redis.asyncio import Redis
except ImportError:
    Redis = None  # type: ignore

from app.core.config import get_settings
from app.core.exceptions import (
    LLMAuthError,
    LLMContentFilterError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    SecurityValidationError,
)
from app.observability.logging import get_logger, observability_middleware, setup_logging
from app.observability.tracing import setup_tracing
from app.admin.routes import router as admin_router
from app.chat import routes as chat_history
from app.db.session import create_db_engine, create_session_factory
from app.routers import chat, documents, features, health, models, rag
from app.services.docintel import ToolCallClient
from app.services.llm_client import create_fallback_llm_client
from app.services.security.rate_limit import rate_limit_middleware
from app.services.vector_store import VectorStore

settings = get_settings()
setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = get_logger()


async def _init_rag(app: FastAPI) -> None:
    """Фоновая инициализация RAG: индексация корпуса и сборка in-memory индекса."""
    try:
        from app.services.ingestion import IngestionService
        from app.services.rag import RAGService

        ingestion = IngestionService(settings)
        app.state.ingestion_service = ingestion
        if ingestion.is_collection_empty():
            logger.info(
                "rag_init: первичная индексация корпуса %s",
                settings.rag_data_dir,
            )
            await asyncio.to_thread(ingestion.ingest_all)

        rag_service = RAGService(settings)
        await asyncio.to_thread(rag_service.build)
        app.state.rag_service = rag_service
        logger.info("rag_ready", collection=settings.rag_collection)
    except Exception as e:
        logger.warning("rag_unavailable", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_tracing()

    app.state.canary = f"CANARY_{secrets.token_hex(4)}"
    logger.info("security_canary_initialized", canary=app.state.canary)

    app.state.llm = create_fallback_llm_client(settings)

    app.state.docintel_client = None
    try:
        app.state.docintel_client = ToolCallClient(settings=settings, provider="primary")
        logger.info(
            "docintel_ready",
            backend=app.state.docintel_client.backend,
            model=app.state.docintel_client.model,
            fallback=settings.docintel.fallback_backend,
        )
    except Exception as e:
        logger.warning("docintel_unavailable", error=str(e))

    app.state.db_engine = None
    app.state.db_session_factory = None
    if settings.chat_repository == "postgres":
        try:
            app.state.db_engine = create_db_engine(settings.database_url)
            app.state.db_session_factory = create_session_factory(app.state.db_engine)
            logger.info("postgres_ready", repository=settings.chat_repository)
        except Exception as e:
            logger.warning("postgres_unavailable", error=str(e))

    app.state.redis = None
    if Redis is not None:
        try:
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            await redis_client.ping()
            app.state.redis = redis_client
        except Exception as e:
            logger.warning("redis_unavailable", error=str(e))

    # Qdrant — опционален: при недоступности сервиса продолжаем без vector-search.
    app.state.vector_store = None
    try:
        vector_store = VectorStore(
            url=settings.qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key is not None
                else None
            ),
            collection=settings.qdrant_collection,
            dim=settings.embedding_dim,
        )
        await vector_store.ensure_collection()
        app.state.vector_store = vector_store
        logger.info(
            "qdrant_ready",
            url=settings.qdrant_url,
            collection=settings.qdrant_collection,
            dim=settings.embedding_dim,
        )
    except Exception as e:
        logger.warning("qdrant_unavailable", error=str(e))

    # Индексация + RAG (LlamaIndex) — в фоне после yield, чтобы /health
    # отвечал сразу и Docker healthcheck не падал на большом корпусе.
    app.state.ingestion_service = None
    app.state.rag_service = None
    app.state.rag_init_task = asyncio.create_task(_init_rag(app))

    yield

    rag_task = getattr(app.state, "rag_init_task", None)
    if rag_task is not None:
        rag_task.cancel()
        try:
            await rag_task
        except asyncio.CancelledError:
            pass

    try:
        llm = app.state.llm
        if hasattr(llm, "aclose"):
            await llm.aclose()
        else:
            await llm.close()
    except Exception:
        pass
    try:
        if app.state.docintel_client is not None:
            await app.state.docintel_client.aclose()
    except Exception:
        pass
    if app.state.redis is not None:
        try:
            await app.state.redis.close()
        except Exception:
            pass
    if app.state.db_engine is not None:
        try:
            await app.state.db_engine.dispose()
        except Exception:
            pass
    if app.state.vector_store is not None:
        try:
            await app.state.vector_store.close()
        except Exception:
            pass
    if app.state.rag_service is not None:
        try:
            await app.state.rag_service.close()
        except Exception:
            pass
    if app.state.ingestion_service is not None:
        try:
            app.state.ingestion_service.close()
        except Exception:
            pass
    from app.observability.tracing import flush_tracing

    flush_tracing()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="FastAPI-сервис для LLM (Б3.4 курса 'ИИ-разработчик')",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-User-ID"],
    expose_headers=["X-Request-ID", "X-LLM-Cost-USD"],
)

app.middleware("http")(observability_middleware)
app.middleware("http")(rate_limit_middleware)

_STATUS_MAP: list[tuple[type[LLMError], int, str]] = [
    (LLMRateLimitError, 429, "llm_rate_limit"),
    (LLMAuthError, 502, "llm_auth"),
    (LLMTimeoutError, 504, "llm_timeout"),
    (LLMContentFilterError, 400, "content_filter"),
    (LLMError, 502, "llm_error"),
]


@app.exception_handler(LLMError)
async def handle_llm_error(request, exc: LLMError):
    for cls, status, code in _STATUS_MAP:
        if isinstance(exc, cls):
            return JSONResponse(
                status_code=status,
                content={"error": {"code": code, "message": str(exc)}},
                headers={"X-Request-ID": getattr(request.state, "request_id", "")},
            )
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "llm_error", "message": str(exc)}},
    )


@app.exception_handler(SecurityValidationError)
async def handle_security_validation(request, exc: SecurityValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "input_rejected",
                "message": str(exc),
                "rule": exc.rule,
            }
        },
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


@app.exception_handler(RequestValidationError)
async def handle_validation(request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "fields": errors}},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


app.include_router(chat_history.router)
app.include_router(admin_router)
app.include_router(chat.router)
app.include_router(features.router)
app.include_router(models.router)
app.include_router(health.router)
app.include_router(rag.router)
app.include_router(documents.router)
