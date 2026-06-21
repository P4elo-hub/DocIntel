import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = PROJECT_ROOT / "app"

FallbackBackend = Literal["ollama", "deepseek"]


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_")

    openai_api_key: SecretStr
    default_model: str = "gpt-4o-mini"
    request_timeout: float = 30.0
    max_retries: int = 3

    @field_validator("openai_api_key")
    @classmethod
    def _openai_api_key_non_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("OPENAI_API_KEY обязателен")
        return value


class DocIntelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCINTEL_", extra="ignore")

    service_name: str = "DocIntel"
    request_timeout_seconds: float = Field(
        default=180.0,
        validation_alias=AliasChoices("request_timeout_seconds", "TIMEOUT_SECONDS"),
    )
    max_tool_rounds: int = 8
    docs_dir: Path = Field(
        default=APP_DIR / "data" / "docs",
        validation_alias=AliasChoices("docs_dir", "DOCS_DIR"),
    )
    knowledge_base_path: Path | None = Field(
        default=APP_DIR / "data" / "knowledge_base.txt",
        validation_alias=AliasChoices("knowledge_base_path", "kb_path", "KB_PATH"),
    )
    methodology_dir: Path = Field(
        default=PROJECT_ROOT / "feature-methodology-project",
        validation_alias=AliasChoices("methodology_dir", "METHODOLOGY_DIR"),
    )
    shablon_path: Path = Field(
        default=PROJECT_ROOT / "feature-methodology-project" / "shablon.md",
        validation_alias=AliasChoices("shablon_path", "SHABLON_PATH"),
    )

    fallback_backend: FallbackBackend = "ollama"
    fallback_api_key: str = "ollama"
    fallback_base_url: str = "http://localhost:11434/v1"
    fallback_model: str = "llama3.2:3b"
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    concurrency: int = 5
    sdk_timeout: float = 30.0
    business_timeout: float = 15.0
    max_tokens: int = 512


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "llm-service"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    rate_limit_per_min: int = Field(
        default=0,
        validation_alias=AliasChoices("rate_limit_per_min", "RATE_LIMIT_PER_MIN"),
    )
    security_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("security_enabled", "SECURITY_ENABLED"),
    )
    # Alias критерия приёмки: OPENAI_API_KEY в .env → llm.openai_api_key
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )
    llm: LLMSettings = Field(default_factory=LLMSettings)
    docintel: DocIntelSettings = Field(default_factory=DocIntelSettings)

    @model_validator(mode="before")
    @classmethod
    def _openai_api_key_alias(cls, data: Any) -> Any:
        """OPENAI_API_KEY — alias для LLM__OPENAI_API_KEY / llm.openai_api_key."""
        if not isinstance(data, dict):
            return data

        llm = dict(data.get("llm") or {})
        top_key = data.get("openai_api_key") or data.get("OPENAI_API_KEY")
        if top_key and "openai_api_key" not in llm:
            llm["openai_api_key"] = top_key
        elif not llm.get("openai_api_key"):
            env_key = os.environ.get("OPENAI_API_KEY")
            if env_key:
                llm["openai_api_key"] = env_key

        data["llm"] = llm
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()
