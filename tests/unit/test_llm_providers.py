"""Тесты разрешения credentials для LLM-провайдеров."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.core.config import DocIntelSettings, LLMSettings, Settings
from app.services.docintel.providers import resolve_llm_credentials


def test_resolve_primary_credentials() -> None:
    settings = Settings(
        llm=LLMSettings(
            openai_api_key=SecretStr("sk-test"),
            default_model="gpt-4o-mini",
        ),
    )
    creds = resolve_llm_credentials(settings, "primary")
    assert creds.backend == "primary"
    assert creds.model == "gpt-4o-mini"
    assert creds.api_key == "sk-test"
    assert creds.base_url == "https://api.openai.com/v1"


def test_resolve_ollama_fallback() -> None:
    settings = Settings(
        docintel=DocIntelSettings(
            fallback_backend="ollama",
            fallback_api_key="ollama",
            fallback_base_url="http://localhost:11434/v1",
            fallback_model="qwen2.5:7b",
        ),
    )
    creds = resolve_llm_credentials(settings, "fallback")
    assert creds.backend == "ollama"
    assert creds.model == "qwen2.5:7b"
    assert creds.base_url == "http://localhost:11434/v1"


def test_resolve_deepseek_fallback() -> None:
    settings = Settings(
        docintel=DocIntelSettings(
            fallback_backend="deepseek",
            deepseek_api_key=SecretStr("sk-ds-test"),
            deepseek_model="deepseek-chat",
        ),
    )
    creds = resolve_llm_credentials(settings, "fallback")
    assert creds.backend == "deepseek"
    assert creds.model == "deepseek-chat"
    assert creds.api_key == "sk-ds-test"
    assert creds.base_url == "https://api.deepseek.com/v1"


def test_resolve_deepseek_fallback_with_override() -> None:
    settings = Settings(
        docintel=DocIntelSettings(
            fallback_backend="ollama",
            deepseek_api_key=SecretStr("sk-ds-test"),
        ),
    )
    creds = resolve_llm_credentials(settings, "fallback", fallback_backend="deepseek")
    assert creds.backend == "deepseek"
    assert creds.api_key == "sk-ds-test"


def test_deepseek_fallback_requires_api_key() -> None:
    settings = Settings(
        docintel=DocIntelSettings(
            fallback_backend="deepseek",
            deepseek_api_key=None,
        ),
    )
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        resolve_llm_credentials(settings, "fallback")
