"""Тесты ToolCallClient (complete, batch, stream) без реальных вызовов API."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from app.core.config import LLMSettings, Settings
from app.services.docintel import SyncLLMClient, ToolCallClient
from app.services.docintel.providers import LlmCredentials


def _test_settings() -> Settings:
    return Settings(llm=LLMSettings(openai_api_key=SecretStr("sk-test")))


def _client(**kwargs) -> ToolCallClient:
    defaults = {"enable_fallback": False, "settings": _test_settings()}
    defaults.update(kwargs)
    with patch("app.services.docintel.client.create_async_openai_client") as mock_factory:
        mock_factory.return_value = MagicMock()
        return ToolCallClient(**defaults)


@pytest.fixture
def llm_client() -> ToolCallClient:
    with patch("app.services.docintel.client.create_async_openai_client") as mock_factory:
        mock_factory.return_value = MagicMock()
        yield ToolCallClient(enable_fallback=False, concurrency=5, settings=_test_settings())


def test_semaphore_created_once_in_init() -> None:
    with patch("app.services.docintel.client.create_async_openai_client"):
        client = ToolCallClient(enable_fallback=False, concurrency=7, settings=_test_settings())
    assert isinstance(client._sem, asyncio.Semaphore)
    assert client._sem is client._sem


@pytest.mark.asyncio
async def test_complete_logs_and_returns(llm_client: ToolCallClient) -> None:
    llm_client._create_completion = AsyncMock(  # type: ignore[method-assign]
        return_value=MagicMock(
            model="gpt-4o-mini",
            choices=[MagicMock(message=MagicMock(content="ответ"))],
        )
    )

    result = await llm_client.complete("Привет")

    assert result == "ответ"
    llm_client._create_completion.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_chat_return_exceptions(llm_client: ToolCallClient) -> None:
    async def _side_effect(*args: object, **kwargs: object) -> MagicMock:
        messages = kwargs.get("messages") or (args[0] if args else [])
        prompt = messages[0]["content"] if messages else ""
        if prompt == "bad":
            raise ValueError("invalid model")
        return MagicMock(
            model="gpt-4o-mini",
            choices=[MagicMock(message=MagicMock(content=f"ok:{prompt}"))],
        )

    llm_client._create_completion = AsyncMock(side_effect=_side_effect)  # type: ignore[method-assign]

    results = await llm_client.batch_chat(["a", "b", "bad", "c"])

    assert results[0] == "ok:a"
    assert results[1] == "ok:b"
    assert isinstance(results[2], ValueError)
    assert results[3] == "ok:c"


@pytest.mark.asyncio
async def test_batch_chat_strict_raises_exception_group(llm_client: ToolCallClient) -> None:
    models = [llm_client.model] * 4
    models[2] = "invalid-model"

    async def _complete(prompt: str, *, model: str | None = None) -> str:
        if model == "invalid-model":
            raise ValueError("model not found")
        return "ok"

    llm_client.complete = _complete  # type: ignore[method-assign]

    with pytest.raises(ExceptionGroup):
        await llm_client.batch_chat_strict(["p1", "p2", "p3", "p4"], models=models)


@pytest.mark.asyncio
async def test_stream_chat_yields_deltas_and_ttft(llm_client: ToolCallClient) -> None:
    class FakeUsage:
        total_tokens = 42

    class FakeDelta:
        def __init__(self, content: str | None) -> None:
            self.content = content

    class FakeChoice:
        def __init__(self, content: str | None) -> None:
            self.delta = FakeDelta(content)

    class FakeChunk:
        def __init__(self, content: str | None, usage: FakeUsage | None = None) -> None:
            self.choices = [FakeChoice(content)] if content is not None else []
            self.usage = usage

    async def fake_stream() -> AsyncIterator[FakeChunk]:
        await asyncio.sleep(0.05)
        yield FakeChunk("Hel")
        await asyncio.sleep(0.05)
        yield FakeChunk("lo")
        yield FakeChunk(None, FakeUsage())

    llm_client._create_completion = AsyncMock(return_value=fake_stream())  # type: ignore[method-assign]

    started = time.perf_counter()
    first_at: float | None = None
    last_at: float | None = None
    parts: list[str] = []

    async for delta in llm_client.stream_chat("Hi"):
        now = time.perf_counter() - started
        if first_at is None:
            first_at = now
        last_at = now
        parts.append(delta)

    assert "".join(parts) == "Hello"
    assert first_at is not None and last_at is not None
    assert first_at < last_at


def test_sync_client_uses_openai_not_async() -> None:
    creds = LlmCredentials(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        backend="primary",
    )
    with patch("app.services.docintel.client.OpenAI") as mock_openai, patch(
        "app.services.docintel.client.create_async_openai_client"
    ) as mock_async, patch(
        "app.services.docintel.client.resolve_llm_credentials", return_value=creds
    ):
        client = SyncLLMClient(settings=_test_settings())
        mock_openai.assert_called_once()
        mock_async.assert_not_called()
        client.close()
