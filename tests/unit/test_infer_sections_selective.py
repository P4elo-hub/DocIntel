"""Селективный выбор секций write: по текущему брифу, не по истории чата."""

from __future__ import annotations

from app.tools.feature_sections import build_execution_plan
from app.tools.write_feature_doc.shablon_loader import infer_sections


YIELD_BRIEF = """
# Контекст для фичи: новый параметр «доходность» в интеграции BPH GetLinkedEvents

В интеграции history-ops ↔ BPH по GetLinkedEvents нужно: (1) добавить новый
параметр в интеграцию, (2) читать из ответа BPH новый параметр «доходность»
(рабочее имя поля — yield), (3) пробросить его на фронт и (4) учесть в
композите BDUI (history-ops-screen-api).
""".strip()


def test_yield_field_change_skips_data_model_and_heavy_as_is() -> None:
    sections = infer_sections(YIELD_BRIEF, "full")
    tools = [s.tool_name for s in build_execution_plan(YIELD_BRIEF)]

    assert "4.1.1" in sections
    assert "1.3-usecase" in sections
    assert "4.2.3" not in sections
    assert "1.2-usecase" not in sections  # нет смены процесса
    assert "write_data_model" not in tools
    assert "write_integration" in tools
    assert "write_use_case_as_is" not in tools


def test_history_word_dannyh_does_not_enable_data_model() -> None:
    polluted = (
        YIELD_BRIEF
        + "\n\nКонтекст диалога:\n"
        "assistant: К сожалению, в предоставленных данных отсутствует полный пример.\n"
        "Также были таблицы markdown в прошлом ответе.\n"
    )
    sections = infer_sections(polluted, "full")
    tools = [s.tool_name for s in build_execution_plan(polluted)]
    assert "4.2.3" not in sections
    assert "write_data_model" not in tools


def test_explicit_db_change_enables_data_model() -> None:
    brief = (
        "GetLinkedEvents: добавить поле yield в ответ и новую таблицу "
        "в PostgreSQL + миграцию liquibase для хранения yield."
    )
    sections = infer_sections(brief, "full")
    tools = [s.tool_name for s in build_execution_plan(brief)]
    assert "4.2.3" in sections
    assert "write_data_model" in tools


def test_plan_uses_fresh_brief_not_history_addon() -> None:
    """Как write_agent: plan_brief = свежий бриф; history не должна роутить kits."""
    plan_brief = YIELD_BRIEF
    history = (
        "В предоставленных данных нет примера. CREATE TABLE trade_order "
        "модель данных postgresql миграция."
    )
    # Ошибочный старый путь: plan по brief+history
    polluted_tools = [
        s.tool_name
        for s in build_execution_plan(f"{plan_brief}\n\n{history}")
    ]
    # Новый путь: plan только по свежему брифу
    fresh_tools = [s.tool_name for s in build_execution_plan(plan_brief)]
    assert "write_data_model" not in fresh_tools
    # История с явными DB-маркерами на старом пути всё ещё могла бы включить —
    # проверяем, что selective path их игнорирует, если plan_brief чистый.
    assert "write_integration" in fresh_tools
    assert polluted_tools  # sanity
