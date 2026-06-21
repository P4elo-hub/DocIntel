"""Сборка сообщений для LLM: порядок ролей и экранирование фигурных скобок."""

from __future__ import annotations

from typing import Any

ROLE_ORDER = {"system": 0, "user": 1, "assistant": 2, "tool": 3}


def escape_format_braces(text: str) -> str:
    """Экранирует { и } для безопасной подстановки в f-string / str.format."""
    return text.replace("{", "{{").replace("}", "}}")


def build_chat_messages(
    *,
    system: str | None = None,
    user: str,
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Формирует список сообщений: system → history → user."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        for item in history:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role in ROLE_ORDER and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user})
    return messages


def format_prompt_template(template: str, **values: str) -> str:
    """Подставляет значения в шаблон после экранирования пользовательского ввода."""
    safe_values = {key: escape_format_braces(val) for key, val in values.items()}
    return template.format(**safe_values)
