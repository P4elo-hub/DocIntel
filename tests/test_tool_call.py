"""Тесты tool_call."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.registry import ToolHandlers
from app.tools.write_feature_doc.shablon_loader import infer_sections, parse_shablon

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "app" / "data" / "docs"
KB_PATH = PROJECT_ROOT / "app" / "data" / "knowledge_base.txt"
METHODOLOGY_DIR = PROJECT_ROOT / "feature-methodology-project"
SHABLON_PATH = METHODOLOGY_DIR / "shablon.md"

KAFKA_BRIEF = """
Сейчас синхронный REST в Notification Service. Перевести на Kafka topic transfer.completed.
Нужны логирование и метрики для producer и consumer.
""".strip()


@pytest.fixture
def handlers() -> ToolHandlers:
    return ToolHandlers(
        knowledge_base_path=KB_PATH,
        docs_dir=DOCS_DIR,
        methodology_dir=METHODOLOGY_DIR,
        shablon_path=SHABLON_PATH,
    )


def test_parse_shablon_finds_sections() -> None:
    sections = parse_shablon(SHABLON_PATH)
    assert "1.1" in sections
    assert "1.2-usecase" in sections
    assert "1.3-usecase" in sections
    assert "Какую бизнес-проблему решает" in sections["1.1"].skeleton


def test_usecase_skeletons_include_scenarios() -> None:
    sections = parse_shablon(SHABLON_PATH)
    for sid, marker in (
        ("1.2-usecase", "Use Case AS IS"),
        ("1.3-usecase", "Use Case TO BE"),
    ):
        skeleton = sections[sid].skeleton
        assert len(skeleton) > 500, f"{sid} skeleton too short"
        assert marker in skeleton
        assert "Основной сценарий" in skeleton
        assert "Альтернативные сценарии" in skeleton
        assert "**Kit" not in skeleton
        assert "Покрывает стандарты" not in skeleton


def test_infer_sections_full_includes_as_is_to_be() -> None:
    sections = infer_sections(KAFKA_BRIEF, "full")
    assert "1.1" in sections
    assert "1.2-usecase" in sections
    assert "1.3-usecase" in sections
    assert "4.1.2" in sections
    assert "5.3.1" in sections
    assert "5.3.2" in sections
    assert "4.2.3" not in sections


def test_write_feature_doc_includes_document_skeleton(handlers: ToolHandlers) -> None:
    result = handlers.write_feature_doc(
        feature_brief=KAFKA_BRIEF,
        protocol="Async",
        feature_name="Уведомления по переводам",
    )
    assert "Скелет итогового документа" in result
    assert "### 1.2. Процесс/Сервис AS IS" in result
    assert "### 1.3. Процесс/Сервис TO BE" in result
    assert "Use Case TO BE" in result
    assert "Основной сценарий TO BE" in result
    skel_start = result.find("## Скелет итогового документа")
    skel_end = result.find("## Справка по kits")
    skeleton = result[skel_start:skel_end]
    assert "> **Kit" not in skeleton
    assert "Покрывает стандарты" not in skeleton
    assert "Контракт выходного документа" in result
    assert "Пакет методологии для фичи" not in result


def test_write_feature_doc_empty_brief(handlers: ToolHandlers) -> None:
    result = handlers.write_feature_doc(feature_brief="  ")
    assert "feature_brief" in result


def test_use_case_skeleton_has_branching_pseudocode(handlers: ToolHandlers) -> None:
    result = handlers.write_feature_doc(
        feature_brief=KAFKA_BRIEF,
        protocol="Async",
        feature_name="Уведомления по переводам",
    )
    skel_start = result.find("## Скелет итогового документа")
    skel_end = result.find("## Справка по kits")
    skeleton = result[skel_start:skel_end]
    assert "ПЕРЕЙТИ К альтернативному сценарию" in skeleton
    assert "ЕСЛИ" in skeleton
    assert "ИНАЧЕ" in skeleton
    assert "Возврат к шагу" in skeleton


def test_nfr_section_5_header_not_duplicated(handlers: ToolHandlers) -> None:
    result = handlers.write_feature_doc(
        feature_brief=KAFKA_BRIEF,
        protocol="Async",
        feature_name="Уведомления по переводам",
    )
    skel_start = result.find("## Скелет итогового документа")
    skel_end = result.find("## Справка по kits")
    skeleton = result[skel_start:skel_end]
    assert skeleton.count("## 5. Нефункциональные требования") == 1
    assert skeleton.count("#### 5.3.1. Требования к логированию") == 1
    assert skeleton.count("#### 5.3.2. Требования к мониторингу") == 1
    assert "#### Логирование —" not in skeleton
    assert "#### Метрики —" not in skeleton


def test_nfr_skeleton_uses_kit_templates(handlers: ToolHandlers) -> None:
    result = handlers.write_feature_doc(
        feature_brief=KAFKA_BRIEF,
        protocol="Async",
        feature_name="Уведомления по переводам",
    )
    skel_start = result.find("## Скелет итогового документа")
    skel_end = result.find("## Справка по kits")
    skeleton = result[skel_start:skel_end]
    assert "## 5. Нефункциональные требования" in skeleton
    assert "#### 5.3.1. Требования к логированию" in skeleton
    assert "#### 5.3.2. Требования к мониторингу" in skeleton
    assert "#### Уровни логирования" in skeleton
    assert "#### Таблица событий для логирования" in skeleton
    assert "### Метрики ошибок" in skeleton

    perf_result = handlers.write_feature_doc(
        feature_brief=f"{KAFKA_BRIEF}\nТребования производительности: p85 latency, RPS.",
        section_id="5.2-performance,5.3.1,5.3.2",
        protocol="Async",
    )
    perf_skel = perf_result[skel_start:perf_result.find("## Справка по kits")]
    assert "### 7.1.1. ВРЕМЯ ОТКЛИКА" in perf_skel or "Endpoint / Операция" in perf_skel


def test_section_package_includes_gap_policy(handlers: ToolHandlers) -> None:
    result = handlers.write_section(
        tool_name="write_requirements",
        feature_brief=KAFKA_BRIEF,
        section_ids=["1.1", "2"],
    )
    assert "GAP / DESIGN (обязательно" in result
    assert "GAP-REQ-001" in result
    assert "Gaps и допущения" in result
    assert "Gap policy для `write_requirements`" in result


def test_search_docs_finds_confluence_import(handlers: ToolHandlers) -> None:
    result = handlers.search_kb("импорт Confluence Markdown")
    assert "docintel-overview.md" in result
