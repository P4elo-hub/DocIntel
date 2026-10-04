"""Answer не получает сырую историю — только вопрос + KB."""

from __future__ import annotations

import inspect

from app.services.docintel import answer_agent


def test_write_answer_from_kb_ignores_chat_history_param() -> None:
    src = inspect.getsource(answer_agent.write_answer_from_kb)
    assert "del chat_history" in src
    assert "## Контекст диалога" not in src
