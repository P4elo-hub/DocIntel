from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings
from app.services.docintel import DocIntelService, ToolCallClient
from app.services.llm import LLMService
from app.services.vector_store import VectorStore

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm(request: Request):
    return request.app.state.llm


def get_cache(request: Request):
    return getattr(request.app.state, "redis", None)


def get_docintel_client(request: Request) -> ToolCallClient:
    client = request.app.state.docintel_client
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="DocIntel недоступен: проверьте OPENAI_API_KEY / LLM__OPENAI_API_KEY в .env",
        )
    return client


LLMDep = Annotated[object, Depends(get_llm)]
CacheDep = Annotated[object, Depends(get_cache)]
DocIntelClientDep = Annotated[ToolCallClient, Depends(get_docintel_client)]


def get_llm_service(
    llm: LLMDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> LLMService:
    return LLMService(llm=llm, cache=cache, ttl=settings.cache_ttl_seconds)


def get_docintel_service(
    client: DocIntelClientDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> DocIntelService:
    return DocIntelService(
        client=client,
        cache=cache,
        ttl=settings.cache_ttl_seconds,
    )


LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]
DocIntelServiceDep = Annotated[DocIntelService, Depends(get_docintel_service)]


def get_session_factory(request: Request):
    return getattr(request.app.state, "db_session_factory", None)


SessionFactoryDep = Annotated[object, Depends(get_session_factory)]


def get_vector_store(request: Request) -> VectorStore | None:
    """Vector-store, инициализированный в lifespan. None — если Qdrant был
    недоступен на старте: роут решает, что делать (503 или fallback)."""
    return getattr(request.app.state, "vector_store", None)


def get_rag_service(request: Request) -> Any:
    """RAG-сервис на LlamaIndex, собранный один раз в lifespan. None — если
    Qdrant/индекс был недоступен на старте: роут отдаёт 503."""
    return getattr(request.app.state, "rag_service", None)


def get_ingestion_service(request: Request) -> Any:
    """Индексатор корпуса (офлайн-контур), собранный в lifespan. None — если
    Qdrant был недоступен на старте: ручки /documents отдают 503."""
    return getattr(request.app.state, "ingestion_service", None)


VectorStoreDep = Annotated[VectorStore | None, Depends(get_vector_store)]
RAGServiceDep = Annotated[Any, Depends(get_rag_service)]
IngestionServiceDep = Annotated[Any, Depends(get_ingestion_service)]
