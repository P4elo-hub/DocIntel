"""Вариант C: встроенный RAG в чат-конвейер — инъекция контекста и цитаты."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.chat.domain import ChatMessage
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.service import ChatService, _filter_used_sources


@pytest.fixture
def json_repo(tmp_path):
    return JsonChatRepository(base_dir=tmp_path)


def _llm_streaming(*tokens: str):
    llm = AsyncMock()

    async def fake_stream():
        for text in tokens:
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content=text))])

    llm.chat.completions.create = AsyncMock(return_value=fake_stream())
    return llm


class _FakeRAG:
    def __init__(self, result: dict) -> None:
        self._result = result
        self.calls: list[str] = []

    async def retrieve_context(self, question: str) -> dict:
        self.calls.append(question)
        return self._result


_CONFIDENT = {
    "context_str": "[1] Возврат за 14 дней.",
    "sources": [
        {"id": 1, "file_name": "refunds.md", "page": 2, "score": 0.7, "snippet": "..."},
        {"id": 2, "file_name": "payment.md", "page": None, "score": 0.4, "snippet": "..."},
    ],
    "top_score": 0.7,
    "confident": True,
}

_NOT_CONFIDENT = {"context_str": "", "sources": [], "top_score": 0.1, "confident": False}


def _service(json_repo, llm, rag) -> ChatService:
    return ChatService(
        repository=json_repo,
        llm_client=llm,
        context_window=5,
        model_context_window=10_000,
        response_tokens=100,
        safety_margin=50,
        rag_service=rag,
        rag_enabled=True,
    )


def test_filter_used_sources_keeps_only_cited():
    sources = [{"id": 1, "file_name": "a.md"}, {"id": 2, "file_name": "b.md"}]
    assert _filter_used_sources("факт [1].", sources) == [{"id": 1, "file_name": "a.md"}]


def test_filter_used_sources_empty_when_no_citations():
    assert _filter_used_sources("нет цитат", [{"id": 1}]) == []


async def test_rag_context_injected_and_sources_emitted(json_repo):
    rag = _FakeRAG(_CONFIDENT)
    llm = _llm_streaming("Возврат ", "за 14 дней [1].")
    service = _service(json_repo, llm, rag)
    chat = await json_repo.create_chat(owner_external_id="u1", interface="telegram")

    events = [e async for e in service.send_message(chat.id, "за сколько вернут деньги?")]

    assert rag.calls == ["за сколько вернут деньги?"]
    # Контекст из базы знаний ушёл в LLM отдельным system-сообщением.
    messages = llm.chat.completions.create.await_args.kwargs["messages"]
    system_texts = " ".join(m["content"] for m in messages if m["role"] == "system")
    assert "[1] Возврат за 14 дней." in system_texts
    # Эмитится событие sources — только реально процитированный [1].
    sources_events = [e for e in events if e.get("type") == "sources"]
    assert sources_events == [{"type": "sources", "sources": [_CONFIDENT["sources"][0]]}]
    # Источники сохранены в сообщении ассистента.
    saved = await json_repo.list_messages(chat.id)
    assert saved[-1].sources == [_CONFIDENT["sources"][0]]


async def test_no_sources_when_not_confident(json_repo):
    rag = _FakeRAG(_NOT_CONFIDENT)
    llm = _llm_streaming("Обычный ", "ответ.")
    service = _service(json_repo, llm, rag)
    chat = await json_repo.create_chat(owner_external_id="u1", interface="telegram")

    events = [e async for e in service.send_message(chat.id, "привет")]

    messages = llm.chat.completions.create.await_args.kwargs["messages"]
    assert all("источники из корпоративной базы" not in str(m["content"]) for m in messages)
    assert not [e for e in events if e.get("type") == "sources"]


async def test_rag_failure_does_not_break_chat(json_repo):
    rag = MagicMock()
    rag.retrieve_context = AsyncMock(side_effect=RuntimeError("qdrant down"))
    llm = _llm_streaming("Ответ", ".")
    service = _service(json_repo, llm, rag)
    chat = await json_repo.create_chat(owner_external_id="u1", interface="telegram")

    tokens = [e["delta"] async for e in service.send_message(chat.id, "вопрос") if e.get("type") == "token"]
    assert "".join(tokens) == "Ответ."


async def test_rag_disabled_skips_retrieval(json_repo):
    rag = _FakeRAG(_CONFIDENT)
    llm = _llm_streaming("Ответ")
    service = ChatService(
        repository=json_repo,
        llm_client=llm,
        context_window=5,
        model_context_window=10_000,
        response_tokens=100,
        safety_margin=50,
        rag_service=rag,
        rag_enabled=False,
    )
    chat = await json_repo.create_chat(owner_external_id="u1", interface="telegram")

    async for _ in service.send_message(chat.id, "вопрос"):
        pass

    assert rag.calls == []


class FakeUploadFile:
    def __init__(self, content_type: str, data: bytes, filename: str = "file"):
        self.content_type = content_type
        self.filename = filename
        self.size = len(data)
        self._data = data

    async def read(self) -> bytes:
        return self._data


async def test_rag_uses_voice_transcript_when_content_empty(json_repo):
    rag = _FakeRAG(_CONFIDENT)
    llm = _llm_streaming("Ответ [1].")
    llm.audio.transcriptions.create = AsyncMock(
        return_value=MagicMock(
            text="сколькими сервисами есть интеграции у истории операций?",
        ),
    )
    service = _service(json_repo, llm, rag)
    chat = await json_repo.create_chat(owner_external_id="u1", interface="telegram")
    media = FakeUploadFile("audio/ogg", b"OggS", "voice.ogg")

    async for _ in service.send_message(chat.id, "", media=media):
        pass

    assert rag.calls == [
        "сколькими сервисами есть интеграции у истории операций?",
    ]
