"""Тесты построения RAG-запросов для follow-up."""

from uuid import uuid4

from app.chat.domain import ChatMessage
from app.chat.rag_query import (
    build_condense_messages,
    build_rag_queries,
    is_follow_up_clarification,
    needs_context_expansion,
    recent_dialog_summary,
    sanitize_condensed,
)


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(chat_id=uuid4(), role=role, content=content)


def test_is_follow_up_clarification_detects_correction():
    assert is_follow_up_clarification("Нет, это не то. Мне нужен другой формат.")
    assert is_follow_up_clarification("из чего формируется сообщение")
    assert not is_follow_up_clarification("как работает история операций")


def test_build_rag_queries_single_for_plain_question():
    assert build_rag_queries("как работает вывод") == ["как работает вывод"]


def test_build_rag_queries_adds_context_for_clarification():
    history = [
        _msg("user", "формат HO в Composite для вывода"),
        _msg(
            "assistant",
            "Пример screenData и sections для funds_output",
        ),
    ]
    queries = build_rag_queries(
        "Нет, это не то — это Composite на фронт, а мне нужен HO в Composite",
        history=history,
    )
    assert len(queries) >= 2
    assert any("Контекст диалога" in q for q in queries)
    assert any("GET_DETAILS" in q and "SEND_DETAILS" in q for q in queries)


def test_build_rag_queries_expands_bph_comparison():
    history = [
        _msg("assistant", "JSON от BPH для вывода"),
        _msg("assistant", "JSON для композита"),
    ]
    queries = build_rag_queries(
        "Сравни JSON: откуда берётся налог?",
        history=history,
    )
    assert any("маппинг" in q.lower() or "TAX_RETAIN" in q for q in queries)


def test_recent_dialog_summary_includes_roles():
    history = [
        _msg("user", "вопрос про вывод"),
        _msg("assistant", "ответ про screenData"),
    ]
    summary = recent_dialog_summary(history)
    assert "Пользователь: вопрос про вывод" in summary
    assert "Ассистент: ответ про screenData" in summary


def test_build_condense_messages_none_without_history():
    assert build_condense_messages("приведи пример", []) is None
    assert build_condense_messages("", [_msg("user", "про комиссии")]) is None


def test_build_condense_messages_includes_current_and_history():
    history = [
        _msg("user", "какой формат комиссий от БПХ в History Ops"),
        _msg("assistant", "через GET_OPERATIONS_WITH_DETAILS"),
    ]
    messages = build_condense_messages("приведи пример джейсона", history)
    assert messages is not None
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "приведи пример джейсона" in user
    assert "GET_OPERATIONS_WITH_DETAILS" in user


def test_build_condense_messages_clarification_excludes_assistant():
    # Явная правка: ошибочный ответ ассистента (Composite/SEND_OPERATIONS_FEED)
    # не должен попасть в контекст condense — иначе поиск уйдёт не на тот слой.
    history = [
        _msg("user", "формат ответа Order Gateway в сторону History Ops"),
        _msg(
            "assistant",
            "Вот JSON SEND_OPERATIONS_FEED от ScreenApi с screenData",
        ),
        _msg("user", "это не то, пришли JSON запроса"),
        _msg("assistant", "пример SEND_OPERATIONS_FEED ..."),
    ]
    current = (
        "Да это вообще не то, это ответ Композита от ScreenApi, "
        "а мне нужен ответ от сервиса OG в сторону HistoryOps"
    )
    messages = build_condense_messages(current, history)
    assert messages is not None
    body = messages[1]["content"]
    assert "SEND_OPERATIONS_FEED" not in body
    assert "screenData" not in body
    assert "Ассистент:" not in body
    assert "Пользователь:" in body
    assert "Order Gateway" in body or "History Ops" in body
    assert current in body


def test_recent_dialog_summary_user_only_roles():
    history = [
        _msg("user", "вопрос про OG"),
        _msg("assistant", "ответ про SEND_OPERATIONS_FEED"),
        _msg("user", "уточнение про History Ops"),
    ]
    summary = recent_dialog_summary(history, limit=3, roles={"user"})
    assert "Пользователь: вопрос про OG" in summary
    assert "Пользователь: уточнение про History Ops" in summary
    assert "SEND_OPERATIONS_FEED" not in summary
    assert "Ассистент:" not in summary


def test_sanitize_condensed_strips_quotes_and_prefix():
    out = sanitize_condensed('Запрос: "пример JSON комиссий БПХ"', fallback="исходный")
    assert out == "пример JSON комиссий БПХ"


def test_sanitize_condensed_falls_back_on_empty():
    assert sanitize_condensed("   ", fallback="исходный вопрос") == "исходный вопрос"


def test_sanitize_condensed_takes_first_line():
    out = sanitize_condensed("пример JSON комиссий\nлишняя строка", fallback="x")
    assert out == "пример JSON комиссий"


def test_needs_context_expansion_true_for_short_and_pronoun():
    assert needs_context_expansion("приведи пример джейсона")
    assert needs_context_expansion("а при чём здесь трансфер?")
    assert needs_context_expansion("это не то")
    # короткая реплика без явных маркеров — тоже follow-up
    assert needs_context_expansion("а джейсон?")


def test_needs_context_expansion_false_for_standalone_question():
    # развёрнутый самостоятельный вопрос (> порога, без маркеров follow-up)
    q = (
        "Какой формат ответа History Ops в сторону Composite при получении "
        "деталей операции по обратному выкупу от DCA"
    )
    assert not needs_context_expansion(q)


def test_needs_context_expansion_false_for_empty():
    assert not needs_context_expansion("")
    assert not needs_context_expansion("   ")
