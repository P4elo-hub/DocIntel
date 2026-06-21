"""Unit-тесты: retry-политика LLMService на 429 и transient errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError, RateLimitError

from app.core.exceptions import LLMRateLimitError
from app.schemas.chat import ChatRequest, Message
from app.services.llm import LLMService


@pytest.fixture
def llm_service(mock_llm, mock_cache):
    return LLMService(llm=mock_llm, cache=None, ttl=3600)


@pytest.fixture
def chat_request() -> ChatRequest:
    return ChatRequest(
        messages=[Message(role="user", content="hi")],
        temperature=0.7,
    )


async def test_rate_limit_429_not_retried(mocker, llm_service, mock_llm, chat_request) -> None:
    mock_llm.chat.completions.create = AsyncMock(
        side_effect=RateLimitError("rate limit", response=MagicMock(), body=None)
    )
    spy_call = mocker.spy(mock_llm.chat.completions, "create")

    with pytest.raises(LLMRateLimitError):
        await llm_service._call(chat_request)

    assert spy_call.await_count == 1


async def test_connection_error_retried_three_times(
    mocker, llm_service, mock_llm, chat_request
) -> None:
    mock_llm.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=MagicMock())
    )
    spy_call = mocker.spy(mock_llm.chat.completions, "create")

    with pytest.raises(Exception):
        await llm_service._call(chat_request)

    assert spy_call.await_count == 3
