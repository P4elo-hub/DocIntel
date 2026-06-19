"""Сборка tools и dispatch по имени."""

from __future__ import annotations

import json
from pathlib import Path

from app.tools.feature_sections import (
    ALL_SECTION_TOOL_NAMES,
    FeatureSectionsHandler,
    build_execution_plan,
    get_all_section_tools,
)
from app.tools.search_kb import SearchKbHandler, get_openai_tool as get_search_kb_tool
from app.tools.write_feature_doc import WriteFeatureDocHandler, get_openai_tool as get_write_feature_doc_tool


def get_openai_tools(service_name: str = "DocIntel", *, include_legacy: bool = False) -> list[dict]:
    """Возвращает список tools для OpenAI API."""
    tools = [get_search_kb_tool(service_name), *get_all_section_tools(service_name)]
    if include_legacy:
        tools.append(get_write_feature_doc_tool(service_name))
    return tools


class ToolHandlers:
    def __init__(
        self,
        knowledge_base_path: Path | None = None,
        docs_dir: Path | None = None,
        methodology_dir: Path | None = None,
        shablon_path: Path | None = None,
    ) -> None:
        self._search = SearchKbHandler(
            knowledge_base_path=knowledge_base_path,
            docs_dir=docs_dir,
        )
        self._sections = FeatureSectionsHandler(
            methodology_dir=methodology_dir,
            shablon_path=shablon_path,
        )
        self._write = WriteFeatureDocHandler(
            methodology_dir=methodology_dir,
            shablon_path=shablon_path,
        )

    def dispatch(self, name: str, arguments: str) -> str:
        payload = json.loads(arguments) if arguments else {}
        if name == "search_kb":
            return self.search_kb(str(payload.get("query", "")))
        if name in ALL_SECTION_TOOL_NAMES:
            return self._dispatch_section_tool(name, payload)
        if name == "write_feature_doc":
            return self.write_feature_doc(
                feature_brief=str(payload.get("feature_brief", "")),
                section_id=payload.get("section_id"),
                protocol=payload.get("protocol"),
                feature_name=payload.get("feature_name"),
            )
        return json.dumps({"error": f"Неизвестный tool: {name}"}, ensure_ascii=False)

    def _dispatch_section_tool(self, name: str, payload: dict) -> str:
        feature_brief = str(payload.get("feature_brief", ""))
        plan = build_execution_plan(feature_brief)
        step = next((item for item in plan if item.tool_name == name), None)
        if step is None:
            return json.dumps(
                {"error": f"Разделы для tool `{name}` не релевантны brief."},
                ensure_ascii=False,
            )
        return self.write_section(
            tool_name=name,
            feature_brief=feature_brief,
            section_ids=list(step.section_ids),
            protocol=payload.get("protocol"),
            feature_name=payload.get("feature_name"),
            context_summary=str(payload.get("context_summary", "")),
            include_document_title=bool(payload.get("include_document_title", False)),
        )

    def search_kb(self, query: str) -> str:
        return self._search.search_kb(query)

    def write_section(
        self,
        tool_name: str,
        feature_brief: str,
        section_ids: list[str],
        *,
        protocol: str | None = None,
        feature_name: str | None = None,
        context_summary: str = "",
        include_document_title: bool = False,
    ) -> str:
        return self._sections.write_section(
            tool_name=tool_name,
            feature_brief=feature_brief,
            section_ids=section_ids,
            protocol=protocol,
            feature_name=feature_name,
            context_summary=context_summary,
            include_document_title=include_document_title,
        )

    def write_feature_doc(
        self,
        feature_brief: str,
        section_id: str | None = None,
        protocol: str | None = None,
        feature_name: str | None = None,
    ) -> str:
        return self._write.write_feature_doc(
            feature_brief=feature_brief,
            section_id=section_id,
            protocol=protocol,
            feature_name=feature_name,
        )
