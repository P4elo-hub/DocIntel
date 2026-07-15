"""AsyncOpenAI-совместимый клиент с fallback primary → DeepSeek для /chat и /chats."""

from __future__ import annotations

from typing import Any

import structlog

from app.chat.media import VOICE_UNAVAILABLE_MESSAGE
from app.core.config import Settings
from app.core.exceptions import VoiceUnavailableError
from app.services.docintel.providers import (
    create_async_openai_client,
    resolve_llm_credentials,
)

logger = structlog.get_logger("llm-client")

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = object  # type: ignore


class _Completions:
    def __init__(self, owner: "FallbackLLMClient") -> None:
        self._owner = owner

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        return await self._owner._create_completion(*args, **kwargs)


class _Chat:
    def __init__(self, owner: "FallbackLLMClient") -> None:
        self.completions = _Completions(owner)


class _Transcriptions:
    def __init__(self, owner: "FallbackLLMClient") -> None:
        self._owner = owner

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._owner._primary.audio.transcriptions.create(
                *args, **kwargs,
            )
        except Exception as exc:
            logger.warning(
                "voice_transcription_primary_failed",
                error=str(exc),
            )
            raise VoiceUnavailableError(VOICE_UNAVAILABLE_MESSAGE) from exc


class _Audio:
    def __init__(self, owner: "FallbackLLMClient") -> None:
        self.transcriptions = _Transcriptions(owner)


class FallbackLLMClient:
    """Прокси вокруг primary AsyncOpenAI с переключением на DeepSeek при ошибке."""

    def __init__(
        self,
        primary: AsyncOpenAI,
        *,
        primary_model: str,
        fallback: AsyncOpenAI | None = None,
        fallback_model: str | None = None,
        enable_fallback: bool = True,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._enable_fallback = enable_fallback and fallback is not None
        self.chat = _Chat(self)
        self.audio = _Audio(self)

    async def _create_completion(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model") or self._primary_model
        kwargs["model"] = model
        try:
            return await self._primary.chat.completions.create(*args, **kwargs)
        except Exception as exc:
            if not self._enable_fallback or self._fallback is None or self._fallback_model is None:
                raise
            logger.warning(
                "llm_primary_failed_using_deepseek_fallback",
                error=str(exc),
                primary_model=model,
                fallback_model=self._fallback_model,
            )
            fallback_kwargs = dict(kwargs)
            fallback_kwargs["model"] = self._fallback_model
            return await self._fallback.chat.completions.create(*args, **fallback_kwargs)

    async def aclose(self) -> None:
        await self._primary.close()
        if self._fallback is not None:
            await self._fallback.close()


def create_fallback_llm_client(settings: Settings) -> FallbackLLMClient | AsyncOpenAI:
    primary_creds = resolve_llm_credentials(settings, "primary")
    primary = create_async_openai_client(
        settings,
        primary_creds,
        timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )

    fallback = None
    fallback_model = None
    if settings.llm.enable_fallback:
        try:
            fallback_creds = resolve_llm_credentials(
                settings,
                "fallback",
                fallback_backend="deepseek",
            )
            fallback = create_async_openai_client(
                settings,
                fallback_creds,
                timeout=settings.llm.request_timeout,
                max_retries=settings.llm.max_retries,
            )
            fallback_model = fallback_creds.model
            logger.info(
                "llm_deepseek_fallback_ready",
                fallback_model=fallback_model,
            )
        except ValueError as exc:
            logger.warning("llm_deepseek_fallback_unavailable", error=str(exc))

    return FallbackLLMClient(
        primary,
        primary_model=primary_creds.model,
        fallback=fallback,
        fallback_model=fallback_model,
        enable_fallback=settings.llm.enable_fallback,
    )
