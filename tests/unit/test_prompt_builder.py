"""Unit-тесты: формирование промптов и экранирование фигурных скобок."""

from __future__ import annotations

from app.prompts.builder import (
    build_chat_messages,
    escape_format_braces,
    format_prompt_template,
)


def test_build_chat_messages_system_before_user() -> None:
    messages = build_chat_messages(
        system="Ты DocIntel.",
        user="Что такое ADR?",
        history=[
            {"role": "assistant", "content": "Предыдущий ответ"},
            {"role": "user", "content": "Уточни"},
        ],
    )
    roles = [m["role"] for m in messages]
    assert roles[0] == "system"
    assert roles[-1] == "user"
    assert roles.index("system") < roles.index("user")


def test_escape_format_braces_prevents_fstring_injection() -> None:
    user_input = "Значение {secret}"
    escaped = escape_format_braces(user_input)
    secret = "LEAKED"
    rendered = f"Ответ: {escaped}"
    assert "LEAKED" not in rendered
    assert "{{secret}}" in rendered


def test_format_prompt_template_safely_injects_user_content() -> None:
    template = "Вопрос: {question}\nКонтекст: {context}"
    result = format_prompt_template(
        template,
        question="Что такое {Kafka}?",
        context="ADR-007",
    )
    assert "Что такое {{Kafka}}?" in result
    assert "ADR-007" in result
