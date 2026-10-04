"""Предобработка текста для retrieval (негации / домен)."""

from __future__ import annotations

from app.chat.media import retrieval_query_text, strip_negated_mentions
from app.chat.rag_query import integration_layer_query_extras
from app.tools.search_kb.handler import extract_api_ids


def test_negation_stripped_from_retrieval_query() -> None:
    raw = (
        "Я тебя спрашиваю про вармаржу, не про Linked Events. "
        "Как выглядит JSON на фронте Композита, деталка?"
    )
    cleaned = retrieval_query_text(raw)
    assert "вармарж" in cleaned.lower() or "вариацион" in cleaned.lower()
    assert "linked" not in cleaned.lower()
    ids = extract_api_ids(cleaned)
    assert not any("linked" in x.lower() for x in ids)


def test_strip_negated_mentions_keeps_positive_topic() -> None:
    assert "ScreenApi" in strip_negated_mentions("ScreenApi, не про GetLinkedEvents")
    assert "GetLinkedEvents" not in strip_negated_mentions(
        "ScreenApi, не про GetLinkedEvents"
    )


def test_rejected_send_operations_stripped_from_retrieval_query() -> None:
    raw = (
        "Интеграционный обмен, GetOperationWithDetails. "
        "Это SendOperations ты прислал, не тот."
    )
    cleaned = retrieval_query_text(raw)
    ids = extract_api_ids(cleaned)
    assert any("GetOperation" in x for x in ids)
    assert not any("SendOperation" in x for x in ids)
    assert "SendOperations" not in cleaned


def test_bph_layer_extra_query_from_cyrillic() -> None:
    extras = integration_layer_query_extras(
        "Нужна операция из БПХ в GetOperationsWithDetails"
    )
    assert extras
    assert any("GET_OPERATIONS_WITH_DETAILS" in e and "BPH" in e for e in extras)


def test_getoperation_singular_aliases_to_plural() -> None:
    ids = extract_api_ids("нужен GetOperationWithDetails из БПХ")
    assert "GetOperationsWithDetails" in ids or "GET_OPERATIONS_WITH_DETAILS" in ids


def test_whisper_get_i_operations_normalized() -> None:
    from app.chat.media import normalize_domain_query

    cleaned = normalize_domain_query(
        "для интеграционного обмена GET и OPERATIONS WITH DETAILS выглядит ответ"
    )
    assert "GET_OPERATIONS_WITH_DETAILS" in cleaned
    ids = extract_api_ids(cleaned)
    assert any("OPERATIONS_WITH_DETAILS" in x for x in ids)
