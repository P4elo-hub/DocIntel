"""Handler kit-tools: пакет для одного standard kit."""

from __future__ import annotations

from pathlib import Path

from app.tools.write_feature_doc.shablon_loader import build_section_package


class FeatureSectionsHandler:
    def __init__(
        self,
        methodology_dir: Path | None = None,
        shablon_path: Path | None = None,
    ) -> None:
        self._methodology_dir = methodology_dir
        self._shablon_path = shablon_path

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
        feature_brief = feature_brief.strip()
        if not feature_brief:
            return "Ошибка: укажите feature_brief."

        if self._methodology_dir is None or self._shablon_path is None:
            return "Ошибка: не настроены пути methodology_dir / shablon_path."

        return build_section_package(
            methodology_dir=self._methodology_dir,
            shablon_path=self._shablon_path,
            feature_brief=feature_brief,
            section_ids=section_ids,
            tool_name=tool_name,
            protocol=protocol,
            feature_name=feature_name,
            context_summary=context_summary,
            include_document_title=include_document_title,
        )
