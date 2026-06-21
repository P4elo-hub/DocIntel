"""Кеш Redis для POST /features/chat."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import LLMSettings, Settings
from app.deps.providers import get_cache, get_docintel_client
from app.main import app
from app.services.docintel import ToolCallClient
from tests.helpers import CASSETS_DIR


class FakeDocIntelClient(ToolCallClient):
    def __init__(self) -> None:
        with patch("app.services.docintel.client.create_async_openai_client"):
            super().__init__(
                enable_fallback=False,
                settings=Settings(llm=LLMSettings(openai_api_key=SecretStr("sk-test"))),
            )
        self.chat_json = AsyncMock(
            return_value={
                "answer": "В проекте 12 документов.",
                "tool_calls_made": 0,
                "model": "gpt-4o-mini",
            }
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_client() -> FakeDocIntelClient:
    return FakeDocIntelClient()


@pytest.mark.asyncio
async def test_features_chat_cache_hit_without_tools(
    fake_client: FakeDocIntelClient,
    mock_cache,
) -> None:
    cached_blob = (CASSETS_DIR / "cache" / "features_chat_hit.json").read_text(
        encoding="utf-8"
    )
    mock_cache.get.return_value = cached_blob

    app.state.docintel_client = fake_client
    app.state.redis = mock_cache
    app.dependency_overrides[get_docintel_client] = lambda: fake_client
    app.dependency_overrides[get_cache] = lambda: mock_cache

    payload = {
        "messages": [{"role": "user", "content": "Сколько документов в проекте?"}],
        "temperature": 0,
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/features/chat", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "из-кеша"
    assert data["cached"] is True
    fake_client.chat_json.assert_not_called()


@pytest.mark.asyncio
async def test_features_chat_does_not_cache_when_tools_used(
    fake_client: FakeDocIntelClient,
    mock_cache,
) -> None:
    fake_client.chat_json.return_value = {
        "answer": "Нашёл документ про gRPC.",
        "tool_calls_made": 2,
        "model": "gpt-4o-mini",
    }

    app.state.docintel_client = fake_client
    app.state.redis = mock_cache
    app.dependency_overrides[get_docintel_client] = lambda: fake_client
    app.dependency_overrides[get_cache] = lambda: mock_cache

    payload = {
        "messages": [{"role": "user", "content": "Найди документ про gRPC"}],
        "temperature": 0,
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/features/chat", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["cached"] is False
    mock_cache.setex.assert_not_called()


@pytest.mark.asyncio
async def test_features_chat_stores_cache_when_no_tools(
    fake_client: FakeDocIntelClient,
    mock_cache,
) -> None:
    app.state.docintel_client = fake_client
    app.state.redis = mock_cache
    app.dependency_overrides[get_docintel_client] = lambda: fake_client
    app.dependency_overrides[get_cache] = lambda: mock_cache

    payload = {
        "messages": [{"role": "user", "content": "Сколько документов в проекте?"}],
        "temperature": 0,
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/features/chat", json=payload)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["cached"] is False
    mock_cache.setex.assert_awaited_once()
    key = mock_cache.setex.await_args.args[0]
    assert key.startswith("features_chat:")
