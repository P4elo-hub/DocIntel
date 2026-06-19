"""Тесты пошаговой генерации по kit-tools."""

from __future__ import annotations

from app.tools.feature_sections import build_execution_plan, merge_section_documents
from tests.test_tool_call import KAFKA_BRIEF


def test_execution_plan_orders_kits_for_kafka_brief() -> None:
    plan = build_execution_plan(KAFKA_BRIEF)
    tool_names = [step.tool_name for step in plan]
    assert tool_names[:4] == [
        "write_requirements",
        "write_use_case_as_is",
        "write_use_case_to_be",
        "write_integration",
    ]
    assert "write_observability" in tool_names
    assert tool_names[-1] == "write_observability"
    assert "4.1.2" in plan[3].section_ids
    obs_step = next(step for step in plan if step.tool_name == "write_observability")
    assert "5.3.1" in obs_step.section_ids


def test_merge_section_documents_adds_title() -> None:
    merged = merge_section_documents(
        "Test Feature",
        ["## 1. Бизнес-требования\n\n### 1.1. Цель\n\nText"],
    )
    assert merged.startswith("# Test Feature")
    assert "### 1.1. Цель" in merged


def test_write_section_package_smaller_than_full_doc() -> None:
    from pathlib import Path

    from app.tools.registry import ToolHandlers
    from tests.test_tool_call import METHODOLOGY_DIR, SHABLON_PATH

    handlers = ToolHandlers(methodology_dir=METHODOLOGY_DIR, shablon_path=SHABLON_PATH)
    full = handlers.write_feature_doc(feature_brief=KAFKA_BRIEF, protocol="Async")
    section = handlers.write_section(
        tool_name="write_observability",
        feature_brief=KAFKA_BRIEF,
        section_ids=["5.3.1", "5.3.2"],
        protocol="Async",
    )
    assert len(section) < len(full) / 2
    assert "## Kit-tool: `write_observability`" in section
    assert "Скелет раздела" in section
