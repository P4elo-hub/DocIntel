"""Парсинг tool call, который локальная LLM иногда пишет текстом вместо tool_calls API."""

from __future__ import annotations

import json
import re
from typing import Any

KNOWN_TOOLS = frozenset({
    "search_kb",
    "write_feature_doc",
    "write_requirements",
    "write_use_case_as_is",
    "write_use_case_to_be",
    "write_integration",
    "write_data_model",
    "write_nfr",
    "write_observability",
})


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _load_json_objects(text: str) -> list[Any]:
    text = _strip_code_fence(text)
    objects: list[Any] = []

    try:
        objects.append(json.loads(text))
        return objects
    except json.JSONDecodeError:
        pass

    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, flags=re.DOTALL):
        try:
            objects.append(json.loads(match.group(0)))
        except json.JSONDecodeError:
            continue

    return objects


def _extract_call(obj: Any, calls: list[tuple[str, str]]) -> None:
    if isinstance(obj, list):
        for item in obj:
            _extract_call(item, calls)
        return

    if not isinstance(obj, dict):
        return

    name = obj.get("name") or obj.get("function") or obj.get("tool")
    if isinstance(name, dict):
        name = name.get("name")

    if not isinstance(name, str) or name not in KNOWN_TOOLS:
        return

    args = obj.get("parameters") or obj.get("arguments") or obj.get("args") or {}
    if isinstance(args, str):
        arguments = args
    else:
        arguments = json.dumps(args, ensure_ascii=False)

    calls.append((name, arguments))


def parse_text_tool_calls(content: str | None) -> list[tuple[str, str]]:
    """Возвращает [(tool_name, arguments_json), ...] из текстового ответа модели."""
    if not content or not content.strip():
        return []

    calls: list[tuple[str, str]] = []
    for obj in _load_json_objects(content):
        _extract_call(obj, calls)

    return calls
