"""Тесты DocIntel SSE-эндпоинта /features/chat/stream."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from pydantic import SecretStr

from app.core.config import LLMSettings, Settings
from app.deps.providers import get_docintel_client
from app.services.docintel import ToolCallClient
from app.main import app


class FakeStreamClient(ToolCallClient):
    async def stream_chat(
        self, prompt: str, *, model: str | None = None, canary: str = ""
    ) -> AsyncIterator[str]:
        yield "Event "
        yield "loop "
        yield "— это механизм asyncio."

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_client() -> FakeStreamClient:
    with patch("app.services.docintel.client.create_async_openai_client"):
        return FakeStreamClient(
            enable_fallback=False,
            settings=Settings(llm=LLMSettings(openai_api_key=SecretStr("sk-test"))),
        )


@pytest.mark.asyncio
async def test_features_chat_stream_sse(fake_client: FakeStreamClient) -> None:
    app.state.docintel_client = fake_client
    app.dependency_overrides[get_docintel_client] = lambda: fake_client
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/features/chat/stream",
                json={"messages": [{"role": "user", "content": "Что такое event loop?"}]},
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")
                body = ""
                async for chunk in response.aiter_text():
                    body += chunk
    finally:
        app.dependency_overrides.clear()

    assert "Event" in body or "event loop" in body.lower()
    assert "[DONE]" in body
