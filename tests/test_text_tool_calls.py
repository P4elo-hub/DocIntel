"""Тесты парсинга текстовых tool call от локальных LLM."""

from __future__ import annotations

from app.services.docintel.text_tool_calls import parse_text_tool_calls


def test_parse_write_feature_doc_from_plain_json() -> None:
    content = (
        '{"name": "write_feature_doc", "parameters": '
        '{"feature_brief": "Kafka уведомления", "section_id": "full", '
        '"protocol": "Async", "feature_name": "transfer-notifications"}}'
    )

    calls = parse_text_tool_calls(content)

    assert len(calls) == 1
    assert calls[0][0] == "write_feature_doc"
    assert "Kafka уведомления" in calls[0][1]
    assert "Async" in calls[0][1]


def test_parse_search_kb_with_arguments_key() -> None:
    content = '{"name": "search_kb", "arguments": {"query": "Confluence import"}}'

    calls = parse_text_tool_calls(content)

    assert calls == [("search_kb", '{"query": "Confluence import"}')]


def test_parse_ignores_unknown_tools() -> None:
    content = '{"name": "unknown_tool", "parameters": {"x": 1}}'

    assert parse_text_tool_calls(content) == []


def test_parse_empty_content() -> None:
    assert parse_text_tool_calls("") == []
    assert parse_text_tool_calls(None) == []
