import os

from opentelemetry import trace
from phoenix.otel import register
from openinference.instrumentation.openai import OpenAIInstrumentor

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
    _initialized = True


def flush_tracing(timeout_millis: int = 5000) -> None:
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if callable(force_flush):
        force_flush(timeout_millis=timeout_millis)
