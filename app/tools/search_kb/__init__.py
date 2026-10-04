"""Tool search_kb — поиск по проектной документации."""

from __future__ import annotations

from app.tools.search_kb.handler import (
    SearchKbHandler,
    chunk_has_contract_body,
    extract_api_ids,
)
from app.tools.search_kb.schema import NAME, get_openai_tool

__all__ = [
    "NAME",
    "SearchKbHandler",
    "chunk_has_contract_body",
    "extract_api_ids",
    "get_openai_tool",
]
