"""Unit-тесты: hit/miss кеша LLMService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.chat import ChatRequest, Message
from app.services.llm import LLMService


def _make_openai_response(content: str = "fresh") -> MagicMock:
    return MagicMock(
        choices=[
            MagicMock(
                message=MagicMock(content=content),
                finish_reason="stop",
            )
        ],
        model="gpt-4o-mini",
        usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.fixture
def llm_service(mock_llm, mock_cache):
    return LLMService(llm=mock_llm, cache=mock_cache, ttl=3600)


@pytest.fixture
def zero_temp_request() -> ChatRequest:
    return ChatRequest(
        messages=[Message(role="user", content="deterministic")],
        temperature=0,
    )


async def test_cache_miss_calls_llm_and_stores(
    mocker, llm_service, mock_llm, mock_cache, zero_temp_request
) -> None:
    mock_cache.get = AsyncMock(return_value=None)
    mock_llm.chat.completions.create = AsyncMock(return_value=_make_openai_response())

    resp = await llm_service.complete(zero_temp_request)

    assert resp.cached is False
    assert resp.content == "fresh"
    mock_llm.chat.completions.create.assert_awaited_once()
    mock_cache.setex.assert_awaited_once()


async def test_cache_hit_skips_llm_call(
    mocker, llm_service, mock_llm, mock_cache, zero_temp_request
) -> None:
    from tests.helpers import CASSETS_DIR

    cached_blob = (CASSETS_DIR / "cache" / "chat_hit.json").read_text(encoding="utf-8")
    mock_cache.get = AsyncMock(return_value=cached_blob)

    resp = await llm_service.complete(zero_temp_request)

    assert resp.cached is True
    assert resp.content == "из-кеша"
    mock_llm.chat.completions.create.assert_not_called()
    mock_cache.setex.assert_not_called()
