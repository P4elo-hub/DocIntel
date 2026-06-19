"""Tool write_feature_doc — написание документации новой фичи."""

from __future__ import annotations

from app.tools.write_feature_doc.handler import WriteFeatureDocHandler
from app.tools.write_feature_doc.schema import NAME, get_openai_tool
from app.tools.write_feature_doc.shablon_loader import infer_sections, parse_shablon

__all__ = [
    "NAME",
    "WriteFeatureDocHandler",
    "get_openai_tool",
    "infer_sections",
    "parse_shablon",
]
