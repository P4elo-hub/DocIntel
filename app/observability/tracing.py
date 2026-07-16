import logging
import os
from importlib.util import find_spec

from opentelemetry import trace
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_initialized = False


def setup_tracing(project_name: str = "diploma-fastapi") -> None:
    global _initialized
    if _initialized:
        return

    endpoint = os.environ.get(
        "PHOENIX_COLLECTOR_ENDPOINT",
        "http://localhost:6006/v1/traces",
    )
    tracer_provider = register(project_name=project_name, endpoint=endpoint)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    # RAG-трейсинг LlamaIndex — опционально: включается PHOENIX_ENABLED=true и
    # группой зависимостей `tracing` (uv sync --extra tracing). Без пакета/флага
    # спаны RAG не пишутся, остальной трейсинг работает как раньше.
    if get_settings().phoenix_enabled:
        if find_spec("openinference.instrumentation.llama_index") is not None:
            from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

            LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
            logger.info("LlamaIndex-трейсинг включён (Phoenix)")
        else:
            logger.warning(
                "phoenix_enabled=true, но пакеты трейсинга LlamaIndex не установлены — "
                "uv sync --extra tracing"
            )

    _initialized = True


def flush_tracing(timeout_millis: int = 5000) -> None:
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if callable(force_flush):
        force_flush(timeout_millis=timeout_millis)
