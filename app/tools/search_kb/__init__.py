"""Tool search_kb — поиск по проектной документации."""

from __future__ import annotations

from app.tools.search_kb.handler import SearchKbHandler
from app.tools.search_kb.schema import NAME, get_openai_tool

__all__ = ["NAME", "SearchKbHandler", "get_openai_tool"]
