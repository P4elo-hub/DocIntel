"""Тесты конфигурации (критерии приёмки)."""

from __future__ import annotations

import os

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings


def test_settings_requires_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM__OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    get_settings.cache_clear()


def test_settings_accepts_openai_api_key_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM__OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-alias-test")
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    assert settings.llm.openai_api_key.get_secret_value() == "sk-alias-test"
    get_settings.cache_clear()


def test_settings_accepts_nested_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    settings = Settings(
        _env_file=None,
        llm={"openai_api_key": SecretStr("sk-nested-test")},
    )
    assert settings.llm.openai_api_key.get_secret_value() == "sk-nested-test"
    get_settings.cache_clear()
