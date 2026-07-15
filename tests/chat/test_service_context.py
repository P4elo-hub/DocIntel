from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.chat.domain import ChatMessage
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.service import ChatService
from app.chat.tokens import count_tokens, fit_to_budget


@pytest.fixture
def json_repo(tmp_path):
    return JsonChatRepository(base_dir=tmp_path)


@pytest.fixture
def mock_llm_client():
    llm = AsyncMock()

    async def fake_stream():
        for text in ["От", "вет"]:
            yield MagicMock(
                choices=[MagicMock(delta=MagicMock(content=text))],
            )

    llm.chat.completions.create = AsyncMock(return_value=fake_stream())
    return llm


@pytest.fixture
def chat_service(json_repo, mock_llm_client):
    return ChatService(
        repository=json_repo,
        llm_client=mock_llm_client,
        context_window=3,
        model_context_window=1000,
        response_tokens=100,
        safety_margin=50,
    )


async def test_sliding_context_includes_system_and_recent(chat_service, json_repo):
    chat = await json_repo.create_chat(
        owner_external_id="u1",
        interface="web",
        system_prompt="Системный промпт",
    )
    for i in range(5):
        await json_repo.append_message(
            chat.id,
            ChatMessage(chat_id=chat.id, role="user", content=f"msg-{i}"),
        )

    chunks = []
    async for event in chat_service.send_message(chat.id, "новый вопрос"):
        if event.get("type") == "token":
            chunks.append(event["delta"])

    assert "".join(chunks) == "Ответ"
    call_kwargs = chat_service.llm.chat.completions.create.await_args.kwargs
    messages = call_kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "Системный промпт"}
    contents = [m["content"] for m in messages if m["role"] == "user"]
    assert contents == ["msg-3", "msg-4", "новый вопрос"]


def test_count_tokens_and_fit_to_budget():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "one"},
        {"role": "user", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    total = count_tokens(messages)
    trimmed = fit_to_budget(messages, budget=total - 5)
    assert trimmed[0]["role"] == "system"
    assert len(trimmed) < len(messages)


def test_count_tokens_handles_multimodal_content():
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "[пользователь сказал голосом]:\nПривет",
                },
            ],
        },
    ]
    assert count_tokens(messages) > 0


async def test_clear_history(chat_service, json_repo):
    chat = await json_repo.create_chat(owner_external_id="u1", interface="cli")
    await json_repo.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="user", content="hello"),
    )
    await chat_service.clear_history(chat.id)
    assert await json_repo.list_messages(chat.id) == []


async def test_send_message_unknown_chat_raises(chat_service):
    with pytest.raises(ValueError, match="not found"):
        async for _ in chat_service.send_message(uuid4(), "hi"):
            pass


class FakeUploadFile:
    def __init__(self, content_type: str, data: bytes, filename: str = "file"):
        self.content_type = content_type
        self.filename = filename
        self.size = len(data)
        self._data = data

    async def read(self) -> bytes:
        return self._data


async def test_send_message_voice_unavailable_returns_error_event(
    chat_service, json_repo, mock_llm_client,
):
    from app.chat.media import VOICE_UNAVAILABLE_MESSAGE

    chat = await json_repo.create_chat(owner_external_id="u1", interface="telegram")
    mock_llm_client.audio.transcriptions.create = AsyncMock(
        side_effect=Exception("401 invalid key"),
    )
    media = FakeUploadFile("audio/ogg", b"OggS", "voice.ogg")

    events = []
    async for event in chat_service.send_message(chat.id, "", media=media):
        events.append(event)

    assert events == [
        {
            "type": "error",
            "code": "voice_unavailable",
            "message": VOICE_UNAVAILABLE_MESSAGE,
        },
    ]
    assert await json_repo.list_messages(chat.id) == []
