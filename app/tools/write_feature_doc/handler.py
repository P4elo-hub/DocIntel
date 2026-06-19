"""Handler: написание документации новой фичи."""

from __future__ import annotations

from pathlib import Path

from app.tools.write_feature_doc.shablon_loader import build_write_package


class WriteFeatureDocHandler:
    def __init__(
        self,
        methodology_dir: Path | None = None,
        shablon_path: Path | None = None,
    ) -> None:
        self._methodology_dir = methodology_dir
        self._shablon_path = shablon_path

    def write_feature_doc(
        self,
        feature_brief: str,
        section_id: str | None = None,
        protocol: str | None = None,
        feature_name: str | None = None,
    ) -> str:
        feature_brief = feature_brief.strip()
        if not feature_brief:
            return "Ошибка: укажите feature_brief — краткое описание фичи."

        if self._methodology_dir is None or self._shablon_path is None:
            return "Ошибка: не настроены пути methodology_dir / shablon_path."

        return build_write_package(
            methodology_dir=self._methodology_dir,
            shablon_path=self._shablon_path,
            feature_brief=feature_brief,
            section_id=section_id,
            protocol=protocol,
            feature_name=feature_name,
        )
