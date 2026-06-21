"""Unit-тесты: парсинг JSON-ответов LLM."""

from __future__ import annotations

import pytest

from app.utils.json_parse import parse_json_object


def test_parse_json_object_from_plain_text() -> None:
    result = parse_json_object('{"relevance": 4, "correctness": 5}')
    assert result["relevance"] == 4
    assert result["correctness"] == 5


def test_parse_json_object_from_markdown_fence() -> None:
    raw = """```json
{"reasoning": "ok", "score": 3}
```"""
    result = parse_json_object(raw)
    assert result["reasoning"] == "ok"
    assert result["score"] == 3


def test_parse_json_object_malformed_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_json_object("{not valid json")


def test_parse_json_object_non_object_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Expected JSON object"):
        parse_json_object("[1, 2, 3]")
