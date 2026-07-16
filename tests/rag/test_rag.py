"""Тесты RAG-контракта и чистых хелперов — без сети (ASGITransport + fake-сервис)."""

import pytest
from httpx import ASGITransport, AsyncClient
from llama_index.core.schema import NodeWithScore, TextNode

from app.deps.providers import get_rag_service, get_session_factory
from app.main import app
from app.services.rag import (
    _contexts_from_nodes,
    build_filters,
    build_sources,
    parse_citations,
)

_HAPPY = {
    "answer": "Возврат оформляется в течение 14 дней [1].",
    "top_score": 0.57,
    "sources": [
        {"id": 1, "file_name": "billing_refunds.md", "page": 2, "score": 0.57, "snippet": "Возврат..."},
        {"id": 2, "file_name": "billing_payment.md", "page": None, "score": 0.35, "snippet": "Оплата..."},
    ],
    "confident": True,
}

_REFUSAL = {
    "answer": "В базе знаний я не нашёл ответа на этот вопрос.",
    "top_score": 0.12,
    "sources": [],
    "confident": False,
}


class _FakeRAG:
    def __init__(self, result: dict) -> None:
        self._result = result

    async def answer(self, question: str) -> dict:
        return self._result


@pytest.fixture
async def rag_client(request):
    rag = request.param
    app.state.rag_service = rag
    app.dependency_overrides[get_rag_service] = lambda: rag
    # Без PG в этих тестах: лог rag_queries no-op'ит при session_factory=None.
    app.dependency_overrides[get_session_factory] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.parametrize("rag_client", [_FakeRAG(_HAPPY)], indirect=True)
async def test_rag_query_returns_answer_and_sources(rag_client: AsyncClient) -> None:
    resp = await rag_client.post("/rag/query", json={"question": "за сколько вернут деньги?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["confident"] is True
    assert body["top_score"] == 0.57
    assert len(body["sources"]) == 2
    assert body["sources"][0] == {
        "id": 1,
        "file_name": "billing_refunds.md",
        "page": 2,
        "score": 0.57,
        "snippet": "Возврат...",
    }


@pytest.mark.parametrize("rag_client", [_FakeRAG(_REFUSAL)], indirect=True)
async def test_rag_query_refusal_is_not_confident(rag_client: AsyncClient) -> None:
    resp = await rag_client.post("/rag/query", json={"question": "чего нет в базе"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["confident"] is False
    assert body["sources"] == []


@pytest.mark.parametrize("rag_client", [None], indirect=True)
async def test_rag_query_503_when_index_unavailable(rag_client: AsyncClient) -> None:
    resp = await rag_client.post("/rag/query", json={"question": "вопрос"})
    assert resp.status_code == 503


@pytest.mark.parametrize("rag_client", [_FakeRAG(_HAPPY)], indirect=True)
async def test_rag_query_rejects_empty_question(rag_client: AsyncClient) -> None:
    resp = await rag_client.post("/rag/query", json={"question": ""})
    assert resp.status_code == 422


def _node(text: str, score: float, file_name: str, page: int | None = None) -> NodeWithScore:
    return NodeWithScore(
        node=TextNode(text=text, metadata={"file_name": file_name, "page": page}),
        score=score,
    )


def test_build_sources_numbers_and_trims_snippet() -> None:
    out = build_sources([_node("Возврат за 14 дней. " * 40, 0.7, "policy.pdf", 3)])
    assert out[0]["id"] == 1
    assert out[0]["file_name"] == "policy.pdf"
    assert out[0]["page"] == 3
    assert out[0]["score"] == 0.7
    assert len(out[0]["snippet"]) <= 200


def test_build_sources_score_is_json_serializable_float() -> None:
    # Regression: reranker (SentenceTransformerRerank) кладёт в score numpy
    # float32 — он не сериализуется в JSON и ронял запись sources в БД, из-за
    # чего пропадал футер «Источники». Приводим к обычному float.
    import json

    from numpy import float32

    sn = NodeWithScore(node=TextNode(text="t", metadata={"file_name": "a.md"}), score=float32(0.283))
    out = build_sources([sn])
    assert type(out[0]["score"]) is float
    json.dumps(out)  # не должно кидать TypeError


def test_build_sources_falls_back_to_source_then_unknown() -> None:
    sn = NodeWithScore(node=TextNode(text="t", metadata={"source": "from_source.md"}), score=0.4)
    assert build_sources([sn])[0]["file_name"] == "from_source.md"
    bare = NodeWithScore(node=TextNode(text="t", metadata={}), score=0.4)
    assert build_sources([bare])[0]["file_name"] == "unknown"


def test_parse_citations_expands_known_ids() -> None:
    sources = [{"id": 1, "file_name": "policy.pdf"}, {"id": 2, "file_name": "faq.md"}]
    text = "Срок 14 дней [1], детали [2]."
    assert parse_citations(text, sources) == "Срок 14 дней [1 — policy.pdf], детали [2 — faq.md]."


def test_parse_citations_leaves_unknown_ids() -> None:
    assert parse_citations("см. [9]", [{"id": 1, "file_name": "a"}]) == "см. [9]"


def test_build_filters_visibility_only() -> None:
    flt = build_filters(visibility="internal")
    assert flt is not None
    assert len(flt.filters) == 1


def test_build_filters_with_departments() -> None:
    flt = build_filters(visibility="internal", departments=["hr", "finance"])
    assert len(flt.filters) == 2


def test_build_filters_none_when_empty() -> None:
    assert build_filters(visibility=None) is None


async def test_retrieve_context_confident_returns_context_and_sources() -> None:
    from app.core.config import get_settings
    from app.services.rag import RAGService

    service = object.__new__(RAGService)
    service._settings = get_settings()
    nodes = [_node("Возврат за 14 дней.", 0.7, "refunds.md")]

    async def fake_retrieve(_q):
        return nodes

    service._retrieve_checked = fake_retrieve

    out = await service.retrieve_context("вопрос")
    assert out["confident"] is True
    assert out["context_str"] == "[1] Возврат за 14 дней."
    assert out["sources"][0]["file_name"] == "refunds.md"


async def test_retrieve_context_below_threshold_is_not_confident() -> None:
    from app.core.config import get_settings
    from app.services.rag import RAGService

    service = object.__new__(RAGService)
    service._settings = get_settings()

    async def fake_retrieve(_q):
        return [_node("нерелевантно", 0.05, "x.md")]

    service._retrieve_checked = fake_retrieve

    out = await service.retrieve_context("вопрос")
    assert out["confident"] is False
    assert out["context_str"] == ""
    assert out["sources"] == []


async def test_retrieve_context_multi_merges_unique_nodes() -> None:
    from app.core.config import get_settings
    from app.services.rag import RAGService

    service = object.__new__(RAGService)
    service._settings = get_settings()
    node_a = _node("SEND_DETAILS proto", 0.62, "composite-be.md")
    node_b = _node("screenData sections", 0.58, "composite-fe.md")
    node_c = _node("SEND_DETAILS fields", 0.55, "composite-be.md")

    async def fake_retrieve(q: str):
        if "GET_DETAILS" in q:
            return [node_a, node_b]
        return [node_c, node_b]

    service._retrieve_checked = fake_retrieve

    out = await service.retrieve_context_multi(
        ["формат вывода", "формат вывода GET_DETAILS SEND_DETAILS"]
    )
    assert out["confident"] is True
    assert "SEND_DETAILS proto" in out["context_str"]
    assert "SEND_DETAILS fields" in out["context_str"]
    assert len(out["sources"]) == 3


async def test_retrieve_context_multi_reserves_slots_for_first_query() -> None:
    # Свежая правка («не ОГ, а Order Gateway») даёт низкие score, а шумная
    # condensed-переформулировка с «ОГЭ» — высокие. С prioritize_first правильный
    # чанк свежей реплики должен попасть в контекст, а не быть вытесненным.
    from app.core.config import get_settings
    from app.services.rag import RAGService

    service = object.__new__(RAGService)
    settings = get_settings()
    settings.rag_rerank_top_n = 2
    service._settings = settings

    raw_hit = _node("order-gateway OG GET_TRADES ответ", 0.30, "og.md")
    noise_1 = _node("ОГЭ экзамен русский язык", 0.99, "school-1.md")
    noise_2 = _node("ОГЭ математика подготовка", 0.98, "school-2.md")

    async def fake_retrieve(q: str):
        if "ОГЭ" in q:
            return [noise_1, noise_2]
        return [raw_hit]

    service._retrieve_checked = fake_retrieve

    out = await service.retrieve_context_multi(
        ["не ОГ, а Order Gateway GET_TRADES", "формат ответа ОГЭ History Ops"],
        prioritize_first=True,
    )
    assert "order-gateway OG GET_TRADES ответ" in out["context_str"]

    # Без приоритета свежая реплика с низким score выпадает за top_n=2.
    without = await service.retrieve_context_multi(
        ["не ОГ, а Order Gateway GET_TRADES", "формат ответа ОГЭ History Ops"],
    )
    assert "order-gateway OG GET_TRADES ответ" not in without["context_str"]


def test_contexts_from_nodes_returns_full_text() -> None:
    # Для RAGAS нужен полный текст чанков, а не усечённый snippet из sources.
    nodes = [
        _node("Возврат товара возможен в течение 14 дней с момента покупки.", 0.8, "a.md"),
        _node("Для возврата нужен чек или номер заказа.", 0.6, "b.md"),
    ]
    assert _contexts_from_nodes(nodes) == [
        "Возврат товара возможен в течение 14 дней с момента покупки.",
        "Для возврата нужен чек или номер заказа.",
    ]
