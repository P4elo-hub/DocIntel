import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.chat.deps import get_chat_service, get_repository
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.service import ChatService
from app.deps.providers import get_llm
from app.main import app


@pytest.fixture
async def chat_client(tmp_path, mock_llm):
    repo = JsonChatRepository(base_dir=tmp_path)

    async def fake_stream():
        for text in ["При", "вет"]:
            yield MagicMock(
                choices=[MagicMock(delta=MagicMock(content=text))],
            )

    mock_llm.chat.completions.create = AsyncMock(return_value=fake_stream())

    service = ChatService(
        repository=repo,
        llm_client=mock_llm,
        context_window=10,
    )

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_llm] = lambda: mock_llm
    app.dependency_overrides[get_chat_service] = lambda: service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


async def test_create_chat(chat_client):
    resp = await chat_client.post(
        "/chats",
        json={
            "owner_external_id": "tg-999",
            "interface": "telegram",
            "system_prompt": "Помощник",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "chat_id" in data


async def test_send_message_stream(chat_client):
    create = await chat_client.post(
        "/chats",
        json={"owner_external_id": "u1", "interface": "web"},
    )
    chat_id = create.json()["chat_id"]

    async with chat_client.stream(
        "POST",
        f"/chats/{chat_id}/messages",
        data={"content": "Привет"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        tokens = []
        done = False
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: ") :])
            if payload.get("type") == "token":
                tokens.append(payload["delta"])
            elif payload.get("type") == "done":
                done = True

    assert "При" in "".join(tokens)
    assert done


async def test_list_and_clear_messages(chat_client):
    create = await chat_client.post(
        "/chats",
        json={"owner_external_id": "u1", "interface": "web"},
    )
    chat_id = create.json()["chat_id"]

    async with chat_client.stream(
        "POST",
        f"/chats/{chat_id}/messages",
        data={"content": "Вопрос"},
    ) as resp:
        async for _ in resp.aiter_lines():
            pass

    list_resp = await chat_client.get(f"/chats/{chat_id}/messages")
    assert list_resp.status_code == 200
    messages = list_resp.json()
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"

    clear_resp = await chat_client.delete(f"/chats/{chat_id}/messages")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["status"] == "ok"

    after_clear = await chat_client.get(f"/chats/{chat_id}/messages")
    assert after_clear.json() == []


async def test_get_chat_not_found(chat_client):
    resp = await chat_client.get(f"/chats/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404
