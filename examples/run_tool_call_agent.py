"""Классический tool calling (search_kb / write_feature_doc) через ToolCallClient."""

from __future__ import annotations

import _bootstrap  # noqa: F401

import argparse
import asyncio
import sys

from openai import APIConnectionError, APITimeoutError

from app.services.docintel import ToolCallClient
from demo_common import close_client, ensure_async_tool_call_client

USER_MESSAGE = (
    "Найди в проектной документации информацию про Confluence import "
    "и кратко опиши, что это такое."
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DocIntel tool calling: search_kb, write_feature_doc и kit-tools.",
    )
    parser.add_argument(
        "--backend",
        choices=("primary", "deepseek", "ollama"),
        default="primary",
        help=(
            "LLM-провайдер: primary=OpenAI (LLM__OPENAI_API_KEY), "
            "deepseek=DeepSeek API, ollama=локальная Ollama. "
            "По умолчанию: primary."
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

    backend_label = {
        "primary": "OpenAI (primary)",
        "deepseek": "DeepSeek API",
        "ollama": "Ollama (локально)",
    }[args.backend]

    print(f"=== {client.settings.docintel.service_name} — tool calling (chat) ===\n")
    print(f"Backend: {backend_label}")
    print(f"Модель: {client.model}\n")
    print(f"Запрос:\n{USER_MESSAGE}\n")
    print("---")

    try:
        result = await client.chat_json(USER_MESSAGE)
    finally:
        await close_client(client)

    print(f"Tool calls: {result['tool_calls_made']} | Модель: {result['model']}")
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
                "Не удалось подключиться к OpenAI API.\n"
                "  • Проверьте интернет / VPN\n"
                "  • Проверьте LLM__OPENAI_API_KEY в .env\n"
                "  • Или запустите через DeepSeek (у вас уже работал):\n"
                "      python examples/run_tool_call_agent.py --backend deepseek",
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
                "  • Запустите: ollama serve && ollama pull qwen2.5:7b",
                file=sys.stderr,
            )
        return 1
    if isinstance(error, APITimeoutError):
        print(
            "Таймаут LLM. Увеличьте DOCINTEL__REQUEST_TIMEOUT_SECONDS в .env.",
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
