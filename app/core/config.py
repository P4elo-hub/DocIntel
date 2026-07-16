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
    base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"
    request_timeout: float = 30.0
    max_retries: int = 3
    enable_fallback: bool = True

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

    chat_repository: Literal["json", "postgres"] = "json"
    chat_storage_dir: Path = Path("./var/chats")
    chat_context_strategy: Literal["sliding", "hybrid"] = "sliding"
    chat_context_window: int = 10
    chat_model_context_window: int = 128_000
    chat_response_tokens: int = 1024
    chat_safety_margin: int = 256
    # Вариант C: встроенный RAG в чат-конвейер. Перед ответом чат ищет
    # релевантные чанки в базе знаний и подмешивает их в контекст с цитатами.
    # Выключить (false) — обычный чат без обращения к базе знаний.
    chat_rag_enabled: bool = True
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/llm_service"

    # Telegram bot / production
    admin_token: SecretStr = SecretStr("change-me-admin")
    internal_token: SecretStr = SecretStr("change-me-internal")
    bot_url: str = "http://bot:9000"
    admin_chat_id: int | None = None
    moderation_use_openai: bool = True
    rate_limit_messages_per_min: int = 15

    # Qdrant ------------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "documents"
    embedding_dim: int = 1536
    embedding_model: str = "text-embedding-3-small"

    # RAG ---------------------------------------------------------------
    # Корпус для индексации и отдельные коллекции под LlamaIndex и bare-metal:
    # один корпус и одна embed-модель, но раскладка payload разная.
    rag_data_dir: Path = Path("data/rag-block-03")
    rag_collection: str = "rag_block_03"
    rag_collection_bare: str = "rag_block_03_bare"
    rag_llm_model: str = "gpt-5.4-mini"
    rag_top_k: int = 3
    rag_chunk_size: int = 1024
    rag_chunk_overlap: int = 128
    # Резать markdown по заголовкам (раздел фичи целиком), а не по предложениям.
    rag_chunk_by_headings: bool = True
    # Пропускать при индексации документы с метаданным deprecated=true.
    rag_skip_deprecated: bool = True
    # OpenAI embeddings: не больше ~300k токенов на HTTP-запрос. На больших .md
    # (таблицы, длинные спеки) batch=100 легко превышает лимит — держим ниже.
    rag_embed_batch_size: int = 32
    # Сколько документов прогонять за один pipeline.run (прогресс + частичный upsert).
    rag_ingest_doc_batch_size: int = 25
    # Если top-1 score ниже порога — ответа в корпусе нет, отдаём честный fallback.
    rag_score_threshold: float = 0.3
    # Корпоративный RAG: достаём широко, оставляем top_n лучших.
    rag_retrieve_top_k: int = 25
    rag_rerank_top_n: int = 10
    # Реранкер и гибридный поиск — опциональные тяжёлые зависимости, в репо не
    # держим хард-депендой. Включаются флагом, тогда нужны extras:
    #   reranker -> pip install sentence-transformers torch  (модель ~600 МБ)
    #   hybrid   -> pip install fastembed
    # По умолчанию выключены; dense-поиск с обрезкой до rag_rerank_top_n работает и так.
    # Реранкер выключен по умолчанию: веса (~2.2 ГБ) качаются с HF при первом
    # build() и блокируют готовность RAG. Включать с HF-кэш-томом (см. docs/rag.md).
    rag_use_reranker: bool = False
    rag_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    # Гибрид выключен: llama-index-vector-stores-qdrant 0.8.8 в hybrid-режиме шлёт
    # устаревший search_batch без имени вектора → Qdrant 400. Требует апгрейда
    # qdrant-client>=1.16 + интеграции >=0.10 (сейчас пин <1.16).
    rag_use_hybrid: bool = False
    rag_sparse_model: str = "Qdrant/bm25"
    # Контроль доступа на уровне поиска: фильтр visibility="internal" до ретрива.
    # Включать только когда корпус проиндексирован через IngestionService
    # (он проставляет visibility); на «голой» коллекции фильтр вернёт пусто.
    rag_restrict_to_internal: bool = False

    # Phoenix-трейсинг LlamaIndex ---------------------------------------
    # Инструментирование LlamaIndex в Phoenix — опциональный runtime-путь,
    # группа зависимостей `tracing` (uv sync --extra tracing). По умолчанию
    # выключено; включается PHOENIX_ENABLED=true, тогда нужен сервис phoenix.
    phoenix_enabled: bool = False

    # Оценка качества (RAGAS) -------------------------------------------
    # Судья и эмбеддинги для офлайн-оценки (scripts/run_eval.py,
    # generate_testset.py) — группа зависимостей `eval`. Судья отделён от
    # production-LLM в /rag/query (rag_llm_model): роли разные, путать нельзя.
    anthropic_api_key: SecretStr | None = None
    eval_judge_provider: Literal["anthropic", "openai"] = "anthropic"
    eval_judge_model: str = "claude-sonnet-4-6"

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def _empty_admin_chat_id(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

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
