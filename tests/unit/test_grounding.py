"""Жёсткая сверка JSON ↔ Qdrant evidence."""

from __future__ import annotations

from app.chat.media import extract_contract_anchors, normalize_domain_query
from app.services.docintel.grounding import (
    check_contract_alignment,
    check_json_grounded,
    evidence_excerpt_answer,
    extract_json_objects,
    gap_refusal_text,
    key_paths,
)
from app.services.docintel.validator import _hard_ground_or_reject


def test_key_paths_nested():
    obj = {
        "history": {
            "feed": {
                "operation": [
                    {"type": "VARMARGIN", "amount": 1},
                ]
            }
        }
    }
    paths = key_paths(obj)
    assert "history" in paths
    assert "history.feed" in paths
    assert "history.feed.operation" in paths
    assert "history.feed.operation[].type" in paths


def test_invented_screendata_fails_against_history_feed():
    evidence = """
Пример из документации:

```json
{
  "history": {
    "feed": {
      "operation": [
        {"type": "VARMARGIN", "sum": 100, "currency": "RUB"}
      ]
    }
  }
}
```
"""
    draft = """
Ответ по вармарже:

```json
{
  "screenData": {
    "type": "OPERATION_HISTORY",
    "content": {
      "totalSum": 100,
      "operations": [
        {"type": "VARMARGIN", "status": "SUCCESS", "amount": 100}
      ]
    }
  }
}
```
"""
    ok, reason = check_json_grounded(draft, evidence)
    assert ok is False
    assert "mismatch" in reason or "without_rag" in reason


def test_matching_history_feed_passes():
    evidence = """
```json
{
  "history": {
    "feed": {
      "operation": [
        {"type": "VARMARGIN", "sum": 100, "currency": "RUB"}
      ]
    }
  }
}
```
"""
    draft = """
```json
{
  "history": {
    "feed": {
      "operation": [
        {"type": "VARMARGIN", "sum": 100, "currency": "RUB"}
      ]
    }
  }
}
```
"""
    ok, reason = check_json_grounded(draft, evidence)
    assert ok is True, reason


def test_draft_json_without_any_rag_json_fails():
    evidence = "В таблице есть поле type и amount, но примера JSON нет."
    draft = """
```json
{
  "screenData": {
    "type": "X",
    "content": {
      "operations": [{"type": "A", "status": "OK", "amount": 1}],
      "totalSum": 1
    }
  }
}
```
"""
    ok, reason = check_json_grounded(draft, evidence)
    assert ok is False
    assert "without_rag_json" in reason


def test_no_substantial_json_passes():
    ok, reason = check_json_grounded("Краткий текстовый ответ без JSON.", "KB text")
    assert ok is True
    assert reason == "no_substantial_json"


def test_hard_ground_answer_returns_gap():
    evidence = '{"history":{"feed":{"operation":[{"type":"X","sum":1}]}}}'
    draft = (
        '```json\n{"screenData":{"type":"Y","content":{"operations":'
        '[{"type":"X","status":"OK","amount":1}],"totalSum":1}}}\n```'
    )
    out = _hard_ground_or_reject(draft, evidence, mode="answer")
    assert out == gap_refusal_text()


def test_hard_ground_document_returns_gap_header():
    evidence = '{"history":{"feed":{"operation":[{"type":"X","sum":1}]}}}'
    draft = (
        '```json\n{"screenData":{"type":"Y","content":{"operations":'
        '[{"type":"X","status":"OK","amount":1}],"totalSum":1}}}\n```'
    )
    out = _hard_ground_or_reject(draft, evidence, mode="document")
    assert out.startswith("# GAP: контракт не подтверждён Qdrant")


def test_extract_json_objects_from_fence():
    text = 'before\n```json\n{"a": {"b": 1, "c": 2}}\n```\nafter'
    objs = extract_json_objects(text)
    assert objs
    assert objs[0]["a"]["b"] == 1


def test_normalize_stt_varmargin_typos():
    assert "вариацион" in normalize_domain_query(
        "операции в рационной мараже на фронте"
    ).lower()
    assert "вариацион" in normalize_domain_query(
        "операция в рационной моржи деталка"
    ).lower()


def test_normalize_linkedin_to_linked_events():
    out = normalize_domain_query(
        "У тебя в LinkedIn.com еще должна быть комиссия"
    )
    assert "linkedin" not in out.lower()
    assert "linked events" in out.lower()
    anchors = extract_contract_anchors(out, "ранее GET_LINKED_EVENTS")
    assert any("GET_LINKED_EVENTS" in a for a in anchors)


def test_contract_alignment_rejects_screendata_for_linked_events():
    draft = """```json
{"screenData":{"type":"operationDetails","data":{"operationType":"comission"}},
 "sections":[{"type":"history.details.header","content":{"title":{"text":"x"}}}]}
```"""
    ok, reason = check_contract_alignment(
        draft,
        "GET_LINKED_EVENTS linkedEvents комиссии связанные",
    )
    assert ok is False
    assert "linked" in reason


def test_evidence_excerpt_prefers_varmargin_json():
    evidence = """
шум coupon_output

```json
{"type": "coupon_output", "sum": 1}
```

| Элемент | Описание |
| --- | --- |
| type | varmargin_input |

```json
{
  "screenData": {
    "type": "operationDetails",
    "data": {"operationType": "varmargin_input"}
  }
}
```
"""
    out = evidence_excerpt_answer(evidence)
    assert "Отказ" not in out
    assert "varmargin" in out.lower()
    assert "JSON из KB" in out
