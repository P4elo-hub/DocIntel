from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings
from app.services.docintel import DocIntelService, ToolCallClient
from app.services.llm import LLMService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm(request: Request):
    return request.app.state.llm


def get_cache(request: Request):
    return request.app.state.redis


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
