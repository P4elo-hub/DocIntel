"""Unit-тесты: валидация Pydantic-схем и маскирование PII в repr."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, Message


def test_message_empty_content_rejected() -> None:
    with pytest.raises(ValidationError):
        Message(role="user", content="")


def test_message_too_long_content_rejected() -> None:
    with pytest.raises(ValidationError):
        Message(role="user", content="x" * 100_001)


def test_chat_request_rejects_assistant_first() -> None:
    with pytest.raises(ValidationError, match="assistant"):
        ChatRequest(
            messages=[Message(role="assistant", content="hi")],
        )


def test_message_repr_masks_pii() -> None:
    msg = Message(
        role="user",
        content="Email ivan@mail.ru карта 4111 1111 1111 1111",
    )
    text = repr(msg)
    assert "ivan@mail.ru" not in text
    assert "[EMAIL]" in text
    assert "[CARD]" in text
