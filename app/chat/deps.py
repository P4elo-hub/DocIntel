from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository, PostgresSystemPromptRepository
from app.chat.repository import ChatRepository
from app.chat.service import ChatService
from app.core.config import Settings, get_settings
from app.deps.providers import get_llm, get_session_factory, SessionFactoryDep
from app.moderation.service import ModerationService

SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession | None]:
    factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state,
        "db_session_factory",
        None,
    )
    if factory is None:
        yield None
        return
    async with factory() as session:
        yield session


DbSessionDep = Annotated[AsyncSession | None, Depends(get_db_session)]


def get_repository(settings: SettingsDep, session: DbSessionDep) -> ChatRepository:
    if settings.chat_repository == "json":
        return JsonChatRepository(base_dir=settings.chat_storage_dir)
    if settings.chat_repository == "postgres":
        if session is None:
            raise HTTPException(
                status_code=503,
                detail="Postgres недоступен: проверьте DATABASE_URL и миграции",
            )
        return PostgresChatRepository(session=session)
    raise ValueError(
        f"Неизвестное значение CHAT_REPOSITORY={settings.chat_repository!r}; "
        "ожидается 'json' или 'postgres'"
    )


def get_chat_service(
    repo: Annotated[ChatRepository, Depends(get_repository)],
    settings: SettingsDep,
    llm=Depends(get_llm),
    session_factory: SessionFactoryDep = None,
) -> ChatService:
    moderation = ModerationService(
        llm_client=llm,
        use_openai_moderation=settings.moderation_use_openai,
        session_factory=session_factory,
    )
    prompt_repo = (
        PostgresSystemPromptRepository(session_factory)
        if session_factory is not None
        else None
    )
    return ChatService(
        repository=repo,
        llm_client=llm,
        default_model=settings.llm.default_model,
        context_window=settings.chat_context_window,
        model_context_window=settings.chat_model_context_window,
        response_tokens=settings.chat_response_tokens,
        safety_margin=settings.chat_safety_margin,
        moderation=moderation,
        prompt_repo=prompt_repo,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
