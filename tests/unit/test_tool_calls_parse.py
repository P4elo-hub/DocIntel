"""Unit-тесты: парсинг tool_calls из текстовых ответов LLM."""

from __future__ import annotations

from app.services.docintel.text_tool_calls import parse_text_tool_calls


def test_parse_tool_calls_from_markdown_fence() -> None:
    content = """```json
{"name": "search_kb", "parameters": {"query": "Confluence import"}}
```"""
    calls = parse_text_tool_calls(content)
    assert len(calls) == 1
    assert calls[0][0] == "search_kb"
    assert "Confluence import" in calls[0][1]


def test_parse_multiple_tool_calls_from_array() -> None:
    content = (
        '[{"name": "search_kb", "arguments": {"query": "Kafka"}}, '
        '{"name": "write_nfr", "parameters": {"feature_brief": "NFR"}}]'
    )
    calls = parse_text_tool_calls(content)
    assert len(calls) == 2
    assert calls[0][0] == "search_kb"
    assert calls[1][0] == "write_nfr"
