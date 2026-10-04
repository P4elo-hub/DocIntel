"""Unit-тесты: lexical expand + API-id contract path."""

from __future__ import annotations

from pathlib import Path

from app.services.docintel.kb_expand import (
    brief_wants_contract,
    contract_gap_answer,
    draft_claims_contract,
    evidence_covers_requested_apis,
    evidence_has_contract_body,
    expand_search_context,
    fetch_lexical_contracts,
)
from app.tools.search_kb.handler import SearchKbHandler, extract_api_ids


def _write_kb(tmp: Path) -> SearchKbHandler:
    gowd = tmp / "GET_OPERATIONS_WITH_DETAILS_BPH.md"
    gowd.write_text(
        """# GET_OPERATIONS_WITH_DETAILS

## Параметры ответа GetOperationsWithDetails

```json
{
  "operations": [
    {"operationType": "TAX_RETAIN", "amount": 10}
  ]
}
```
""",
        encoding="utf-8",
    )
    doc = tmp / "SIHIST-3502_GET_LINKED_EVENTS.md"
    doc.write_text(
        """# GET_LINKED_EVENTS

## Содержание

Оглавление.

## Параметры запроса GET_LINKED_EVENTS

| Параметр | Тип | Описание |
|---|---|---|
| agreement | string | договор |
| operationTypes | array | типы |

```json
{
  "agreement": "123",
  "operationTypes": ["transaction_buy", "transaction_sell"]
}
```

## Параметры ответа linkedEvents

```json
{
  "linkedEvents": [
    {"externalSystemId": "1", "operationType": "BUY"}
  ]
}
```
""",
        encoding="utf-8",
    )
    og = tmp / "GetTradeOrders_OG.md"
    og.write_text(
        """# Order Gateway GetTradeOrders

## Параметры запроса GetTradeOrdersRequest

```json
{
  "GetTradeOrdersRequest": {
    "startDate": "2024-01-01",
    "endDate": "2024-01-31",
    "is_active": true
  }
}
```
""",
        encoding="utf-8",
    )
    noise = tmp / "logging.md"
    noise.write_text(
        """# Логирование операций

## Мониторинг

Prometheus metrics for operations history.
""",
        encoding="utf-8",
    )
    return SearchKbHandler(docs_dir=tmp)


def test_extract_api_ids_linked_events_and_trade_orders() -> None:
    ids = extract_api_ids(
        "Нужны примеры GET_LINKED_EVENTS и GetTradeOrders для Order Gateway"
    )
    assert "GET_LINKED_EVENTS" in ids
    assert "GetTradeOrders" in ids or "GetTradeOrdersRequest" in ids or any(
        "tradeorders" in x.lower().replace("_", "") for x in ids
    )


def test_fetch_api_contracts_returns_json_not_logging(tmp_path: Path) -> None:
    kb = _write_kb(tmp_path)
    pack = kb.fetch_api_contracts("GET_LINKED_EVENTS пример ответа")
    assert "linkedEvents" in pack
    assert "transaction_buy" in pack
    assert "Prometheus" not in pack


def test_grep_kb_and_read_kb_section(tmp_path: Path) -> None:
    kb = _write_kb(tmp_path)
    grep_hit = kb.grep_kb("GetTradeOrdersRequest JSON")
    assert "GetTradeOrdersRequest" in grep_hit
    assert "startDate" in grep_hit

    section = kb.read_kb_section("GetTradeOrders_OG.md", "Параметры запроса")
    assert "is_active" in section


def test_expand_search_context_rag_first_only_on_gap(tmp_path: Path) -> None:
    kb = _write_kb(tmp_path)
    # Дырка: lexical (целевой API) идёт ПЕРЕД RAG, чтобы answer его не обрезал.
    rag = "[1] Какой-то процесс дедупликации HO шаг 9"
    merged = expand_search_context(
        kb,
        query="GET_LINKED_EVENTS request response пример",
        rag_context=rag,
    )
    assert "Контракты из файлов KB" in merged
    assert merged.index("Контракты из файлов KB") < merged.index("RAG (Qdrant)")
    assert "linkedEvents" in merged
    assert "дедупликации" in merged

    # Контракт уже в RAG → lexical не трогаем.
    rag_ok = '```json\n{"linkedEvents": [{"id": "1"}]}\n```\n'
    merged_ok = expand_search_context(
        kb,
        query="GET_LINKED_EVENTS request response пример",
        rag_context=rag_ok,
    )
    assert "RAG (Qdrant)" in merged_ok
    assert "Контракты из файлов KB" not in merged_ok
    assert "linkedEvents" in merged_ok

    # В RAG чужой контракт (SendOperations) → дырка по целевому API → lexical.
    rag_wrong = (
        "## SendOperations\n```json\n"
        '{"screenData": {"sections": []}}\n```\n'
    )
    merged_gap = expand_search_context(
        kb,
        query="GetOperationsWithDetails из БПХ пример JSON",
        rag_context=rag_wrong,
    )
    assert "Контракты из файлов KB" in merged_gap
    assert "TAX_RETAIN" in merged_gap or "GetOperationsWithDetails" in merged_gap


def test_evidence_covers_requested_apis_rejects_wrong_exchange() -> None:
    wrong = '```json\n{"screenData": []}\n```\nSendOperations feed'
    assert not evidence_covers_requested_apis(
        wrong, "нужен GetOperationsWithDetails из БПХ"
    )
    right = (
        'GetOperationsWithDetails\n```json\n'
        '{"operations": [{"operationType": "TAX_RETAIN"}]}\n```'
    )
    assert evidence_covers_requested_apis(
        right, "нужен GetOperationsWithDetails из БПХ"
    )


def test_evidence_and_gap_helpers() -> None:
    assert evidence_has_contract_body('```json\n{"a": 1}\n```')
    assert draft_claims_contract('Вот пример:\n```json\n{"x": 1}\n```')
    assert brief_wants_contract("дай пример JSON для обмена")
    gap = contract_gap_answer("нужен GET_LINKED_EVENTS")
    assert "нет полного примера" in gap.lower()
    assert "GET_LINKED_EVENTS" in gap


def test_fetch_lexical_contracts_empty_without_match(tmp_path: Path) -> None:
    kb = SearchKbHandler(docs_dir=tmp_path)
    assert fetch_lexical_contracts(kb, "GET_LINKED_EVENTS") == ""
