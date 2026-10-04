"""Answer не получает сырую историю — только вопрос + KB."""

from __future__ import annotations

import inspect

from app.services.docintel import answer_agent


def test_answer_agent_refuses_missing_operation_example() -> None:
    text = answer_agent._SYSTEM
    assert "ЗАПРЕТ НА СОБРАННЫЙ ПРИМЕР" in text
    assert "такого примера в базе нет" in text
    assert "Не собирай JSON" in text


def test_form_example_request_is_answer_not_write() -> None:
    from app.services.agent_graph import detect_intent_heuristic

    text = (
        "Это пример funds transfer. Сформируй пример transaction_buy "
        "в Send Operations, блоки будут другие."
    )
    assert detect_intent_heuristic(text) == "answer"


def test_write_answer_from_kb_ignores_chat_history_param() -> None:
    src = inspect.getsource(answer_agent.write_answer_from_kb)
    assert "del chat_history" in src
    assert "## Контекст диалога" not in src
