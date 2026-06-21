"""Парсинг JSON-ответов LLM (plain text и markdown-fence)."""

from __future__ import annotations

import json
import re


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


def parse_json_object(text: str) -> dict:
    """Извлекает JSON-объект из текста. Raises ValueError при невалидном JSON."""
    stripped = _strip_code_fence(text.strip())
    try:
        result = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")

    return result


def parse_json_object_lenient(text: str) -> dict:
    """Пробует распарсить JSON-объект, включая вложенный фрагмент в тексте."""
    try:
        return parse_json_object(text)
    except ValueError:
        pass

    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, flags=re.DOTALL):
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            return result

    raise ValueError("Invalid JSON: no JSON object found")
