"""Sectioned-генерация документации фичи через ToolCallClient."""

from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import asyncio
import sys

from openai import APIConnectionError, APITimeoutError

from app.services.docintel import ToolCallClient
from demo_common import (
    FEATURE_BRIEF,
    FEATURE_NAME,
    FEATURE_PROTOCOL,
    close_client,
    ensure_async_tool_call_client,
    save_answer,
)

BACKEND_LABELS = {
    "primary": "OpenAI (primary)",
    "deepseek": "DeepSeek API",
    "ollama": "Ollama (локально)",
}

ANSWER_SUFFIX = {
    "primary": "openai",
    "deepseek": "deepseek",
    "ollama": "local",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DocIntel: sectioned-генерация документации фичи (kit-tools).",
    )
    parser.add_argument(
        "--backend",
        choices=("primary", "deepseek", "ollama"),
        default="primary",
        help=(
            "LLM-провайдер. primary=OpenAI, deepseek=DeepSeek, ollama=локально. "
            "Если OpenAI недоступен — используйте: --backend deepseek"
        ),
    )
    return parser.parse_args()


def _make_client(backend: str) -> ToolCallClient:
    if backend == "primary":
        return ToolCallClient(provider="primary", enable_fallback=True)
    return ToolCallClient(
        provider="fallback",
        fallback_backend=backend,  # type: ignore[arg-type]
        enable_fallback=False,
    )


async def main(args: argparse.Namespace) -> int:
    ensure_async_tool_call_client()
    client = _make_client(args.backend)
    settings = client.settings

    print(
        f"=== {settings.docintel.service_name} — документация фичи "
        f"(sectioned / {BACKEND_LABELS[args.backend]}) ===\n"
    )
    print(f"Модель: {client.model}\n")
    print(f"Запрос:\n{FEATURE_BRIEF}\n")
    print(
        f"Таймаут: {settings.docintel.request_timeout_seconds}s на секцию\n"
        "Режим: kit-tool → секция → склейка (несколько LLM-вызовов)\n"
        "Генерация может занять 3–8 минут...\n"
    )
    print("---")

    try:
        result = await client.chat_sectioned_json(
            FEATURE_BRIEF,
            feature_name=FEATURE_NAME,
            protocol=FEATURE_PROTOCOL,
        )
    finally:
        await close_client(client)

    output_path = save_answer(result, suffix=ANSWER_SUFFIX[args.backend])

    print(f"Tool calls: {result['tool_calls_made']} | Модель: {result['model']}")
    print(f"Сохранено: {output_path}")
    print(f"\nОтвет:\n{result['answer']}\n")

    return 0


def _handle_error(error: BaseException, *, backend: str) -> int:
    if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)):
        print("\nПрервано пользователем (Ctrl+C).", file=sys.stderr)
        return 130
    if isinstance(error, ValueError):
        print(error, file=sys.stderr)
        return 1
    if isinstance(error, APIConnectionError):
        if backend == "primary":
            print(
                "Не удалось подключиться к OpenAI (и fallback Ollama тоже недоступен).\n"
                "  • Проверьте LLM__OPENAI_API_KEY и интернет / VPN\n"
                "  • Или используйте DeepSeek (у вас уже работал):\n"
                "      python examples/run_tool_call.py --backend deepseek\n"
                "      python examples/run_tool_call_deepseek.py",
                file=sys.stderr,
            )
        elif backend == "deepseek":
            print(
                "Не удалось подключиться к DeepSeek API.\n"
                "  • Проверьте DOCINTEL__DEEPSEEK_API_KEY в .env",
                file=sys.stderr,
            )
        else:
            print(
                "Не удалось подключиться к Ollama.\n"
                "  • ollama serve && ollama pull qwen2.5:7b",
                file=sys.stderr,
            )
        return 1
    if isinstance(error, APITimeoutError):
        print(
            "Запрос к LLM не уложился в таймаут. "
            "Увеличьте DOCINTEL__REQUEST_TIMEOUT_SECONDS в .env (например, 300).",
            file=sys.stderr,
        )
        return 1
    raise error


if __name__ == "__main__":
    cli_args = _parse_args()
    try:
        raise SystemExit(asyncio.run(main(cli_args)))
    except BaseException as error:
        raise SystemExit(_handle_error(error, backend=cli_args.backend)) from error
