"""Разрешение credentials для primary / fallback (Ollama | DeepSeek API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI
from pydantic import SecretStr

from app.core.config import DocIntelSettings, LLMSettings, Settings

ProviderKind = Literal["primary", "fallback"]
FallbackBackend = Literal["ollama", "deepseek"]

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class LlmCredentials:
    api_key: str
    base_url: str
    model: str
    backend: FallbackBackend | Literal["primary"]


def _secret(value: SecretStr | None) -> str | None:
    if value is None:
        return None
    raw = value.get_secret_value()
    return raw or None


def resolve_llm_credentials(
    settings: Settings,
    provider: ProviderKind,
    *,
    fallback_backend: FallbackBackend | None = None,
) -> LlmCredentials:
    llm: LLMSettings = settings.llm
    docintel: DocIntelSettings = settings.docintel

    if provider == "primary":
        api_key = _secret(llm.openai_api_key)
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY (или LLM__OPENAI_API_KEY) не задан. "
                "Скопируйте .env.example в .env и укажите ключ."
            )
        return LlmCredentials(
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            model=llm.default_model,
            backend="primary",
        )

    backend = fallback_backend or docintel.fallback_backend
    if backend == "deepseek":
        api_key = _secret(docintel.deepseek_api_key)
        if not api_key:
            raise ValueError(
                "DeepSeek не настроен. Укажите DOCINTEL__DEEPSEEK_API_KEY в .env "
                "(ключ: https://platform.deepseek.com)."
            )
        return LlmCredentials(
            api_key=api_key,
            base_url=docintel.deepseek_base_url or DEEPSEEK_DEFAULT_BASE_URL,
            model=docintel.deepseek_model or DEEPSEEK_DEFAULT_MODEL,
            backend="deepseek",
        )

    api_key = docintel.fallback_api_key
    base_url = docintel.fallback_base_url
    if not api_key or not base_url:
        raise ValueError(
            "Ollama не настроена. Укажите DOCINTEL__FALLBACK_API_KEY и "
            "DOCINTEL__FALLBACK_BASE_URL в .env (например: http://localhost:11434/v1)."
        )
    return LlmCredentials(
        api_key=api_key,
        base_url=base_url,
        model=docintel.fallback_model,
        backend="ollama",
    )


def create_async_openai_client(
    settings: Settings,
    creds: LlmCredentials,
    *,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> AsyncOpenAI:
    """OpenAI-compatible AsyncOpenAI для primary / Ollama / DeepSeek."""
    docintel = settings.docintel
    llm = settings.llm
    return AsyncOpenAI(
        api_key=creds.api_key,
        base_url=creds.base_url,
        timeout=timeout if timeout is not None else docintel.sdk_timeout,
        max_retries=max_retries if max_retries is not None else llm.max_retries,
    )
