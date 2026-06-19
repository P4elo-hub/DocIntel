"""Общая логика демо fallback (Ollama / DeepSeek API)."""

from __future__ import annotations

import _bootstrap  # noqa: F401

import asyncio
import sys

from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
)

from demo_common import (
    FEATURE_BRIEF,
    FEATURE_NAME,
    FEATURE_PROTOCOL,
    close_client,
    ensure_async_tool_call_client,
    save_answer,
)
from app.core.config import get_settings
from app.services.docintel import ToolCallClient
from app.services.docintel.providers import FallbackBackend


async def run_sectioned_fallback_demo(*, backend: FallbackBackend, answer_suffix: str) -> int:
    ensure_async_tool_call_client()
    settings = get_settings()
    client = ToolCallClient(provider="fallback", fallback_backend=backend)
    backend_label = "Ollama (локально)" if backend == "ollama" else "DeepSeek API"

    print(
        f"=== {settings.docintel.service_name} — документация фичи "
        f"(sectioned / fallback / {backend_label}) ===\n"
    )
    print(f"Backend: {backend}")
    print(f"Модель: {client.model}")
    if backend == "ollama":
        print(f"Base URL: {settings.docintel.fallback_base_url}\n")
    else:
        print(f"Base URL: {settings.docintel.deepseek_base_url}\n")

    print(f"Запрос:\n{FEATURE_BRIEF}\n")
    print(
        f"Таймаут: {settings.docintel.request_timeout_seconds}s на секцию\n"
        "Режим: kit-tool → секция → склейка (несколько LLM-вызовов)\n"
    )
    if backend == "ollama":
        print(
            "Убедитесь, что Ollama запущена и модель скачана:\n"
            "  ollama serve && ollama pull qwen2.5:7b\n"
        )
    else:
        print("Нужен ключ DOCINTEL__DEEPSEEK_API_KEY (platform.deepseek.com).\n")
    print(
        "При таймаутах увеличьте DOCINTEL__REQUEST_TIMEOUT_SECONDS в .env (например, 300).\n"
        "---"
    )

    try:
        result = await client.chat_sectioned_json(
            FEATURE_BRIEF,
            feature_name=FEATURE_NAME,
            protocol=FEATURE_PROTOCOL,
        )
    finally:
        await close_client(client)

    output_path = save_answer(result, suffix=answer_suffix)

    print(f"Kit-tools (секций): {result['tool_calls_made']} | Модель: {result['model']}")
    print(f"Сохранено: {output_path}")
    print(f"\nОтвет:\n{result['answer']}\n")
    return 0


def handle_fallback_demo_errors(error: BaseException, *, backend: str) -> int:
    if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)):
        print("\nПрервано пользователем (Ctrl+C).", file=sys.stderr)
        return 130

    settings = get_settings()
    if isinstance(error, ValueError):
        print(error, file=sys.stderr)
        return 1
    if isinstance(error, AuthenticationError):
        if backend == "deepseek":
            print(
                "DeepSeek отклонил API-key. Проверьте DOCINTEL__DEEPSEEK_API_KEY в .env.",
                file=sys.stderr,
            )
        else:
            print("Ошибка авторизации fallback API.", file=sys.stderr)
        return 1
    if isinstance(error, APIConnectionError):
        if backend == "deepseek":
            print("Не удалось подключиться к DeepSeek API.", file=sys.stderr)
        else:
            print(
                "Не удалось подключиться к Ollama. Запустите сервер:\n  ollama serve",
                file=sys.stderr,
            )
        return 1
    if isinstance(error, BadRequestError) and "does not support tools" in str(error):
        model = settings.docintel.fallback_model
        print(
            f"Модель {model!r} не поддерживает tool calling.\n"
            "  ollama pull qwen2.5:7b",
            file=sys.stderr,
        )
        return 1
    if isinstance(error, PermissionDeniedError) and (
        "requires a subscription" in str(error) or "upgrade" in str(error)
    ):
        model = settings.docintel.fallback_model
        print(
            f"Модель {model!r} доступна только по подписке Ollama Pro.\n"
            "  python examples/run_tool_call_deepseek.py + DOCINTEL__DEEPSEEK_API_KEY",
            file=sys.stderr,
        )
        return 1
    if isinstance(error, APIStatusError) and (
        error.status_code == 402 or "Insufficient Balance" in str(error)
    ):
        print(
            "На аккаунте DeepSeek недостаточно баланса (402 Insufficient Balance).",
            file=sys.stderr,
        )
        return 1
    if isinstance(error, APITimeoutError):
        print(
            "Запрос к LLM не уложился в таймаут. "
            "Увеличьте DOCINTEL__REQUEST_TIMEOUT_SECONDS в .env.",
            file=sys.stderr,
        )
        return 1
    raise error
