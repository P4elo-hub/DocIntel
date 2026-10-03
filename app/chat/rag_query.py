"""Построение RAG-запросов с учётом контекста диалога.

Follow-up и уточнения про слой интеграции (BPH→HO, HO→Composite, Composite→МП)
часто теряют контекст, если искать только по последней реплике. Здесь
расширяем запрос историей и ключевыми терминами нужного слоя.
"""

from __future__ import annotations

import re

from app.chat.domain import ChatMessage
from app.chat.media import _VOICE_PREFIX

_CLARIFICATION_RE = re.compile(
    r"не\s+то\b|не\s+тот\b|это\s+не\b|уточн|в\s+прошл|ранее|ты\s+(?:в\s+)?прошл|"
    r"имел(?:\s+в\s+виду|\s+ввиду)|а\s+мне\s+нужн|из\s+чего\s+формиру|"
    r"не\s+(?:тот\s+)?(?:слой|формат|пример)|wrong|not\s+what",
    re.IGNORECASE,
)

_DIALOG_REFERENCE_RE = re.compile(
    r"эти(?:х|\s+два)|прошл|ранее|"
    r"ты\s+(?:присл|отправ|показ|дал|прин|привел|привёл|написал)|"
    r"данн(?:ого|ой|ый|ую|ое|ом)|текущ\w*|предыдущ\w*|"
    r"в\s+данном\s+(?:обмене|формате|примере|ответе)|"
    r"в\s+этом\s+(?:обмене|формате|примере|ответе)|"
    r"насколько\s+я\s+помню|"
    r"в\s+тот\s+формат|в\s+этот\s+формат|трансформ|"
    r"последн(?:ий|ие)\s+(?:json|джейсон|сообщ|пример|операц)|из\s+чего|"
    r"history\s*ops|screen\s*api|композит|бph|bph",
    re.IGNORECASE,
)

_HO_TO_COMPOSITE_RE = re.compile(
    r"history\s*ops|истори[яи]\s*операц|(?:в\s+)?composite|композит|screen\s*api|"
    r"send_details|get_details|ho\s*[→\->]+\s*composite",
    re.IGNORECASE,
)

_FRONTEND_LAYER_RE = re.compile(
    r"фронт|screenData|sections|на\s+м[пп]|клиент(?:у|а)?|отправляет\s+на\s+фронт",
    re.IGNORECASE,
)

_BPH_LAYER_RE = re.compile(r"бph|bph|brokerage\s*portfolio", re.IGNORECASE)

_MAPPING_RE = re.compile(
    r"сравн|откуда\s+бер|маппинг|налог|tax|комисси|fee|поле",
    re.IGNORECASE,
)


def is_follow_up_clarification(text: str) -> bool:
    """Последняя реплика явно уточняет или исправляет предыдущий ответ."""
    return bool(_CLARIFICATION_RE.search(text or ""))


# Реплика короче этого — почти всегда follow-up («приведи пример», «а джейсон?»),
# который без контекста диалога теряет тему.
SHORT_FOLLOWUP_MAX_LEN = 80

_FOLLOWUP_HINT_RE = re.compile(
    r"^\s*(?:а\s+)?(?:приведи|покаж|дай\b|пример|ещ[её]\b|подробн|уточни|распиш|"
    r"а\s+как|а\s+что|а\s+где|а\s+поч|а\s+при\s+ч[её]м|тогда\b|и\s+что|"
    r"это\s+не|нет,|не\s+то\b|не\s+тот\b)",
    re.IGNORECASE,
)


def needs_context_expansion(current: str) -> bool:
    """Нужен ли контекст диалога (condense + multi-query) для этой реплики.

    True для follow-up: коротких реплик, местоименных/уточняющих формулировок
    или явных ссылок на предыдущие сообщения. Самостоятельные развёрнутые
    вопросы обрабатываем одним запросом — без лишнего LLM-вызова и мульти-поиска.
    """
    text = (current or "").strip()
    if not text:
        return False
    # Только маркеры follow-up: явная правка/уточнение, местоименное начало
    # («приведи пример», «а при чём…», «нет,…») или короткая реплика. Доменные
    # термины (History Ops, композит) НЕ считаем follow-up — иначе почти любой
    # предметный вопрос зря уходил бы в condense + мульти-поиск.
    if is_follow_up_clarification(text):
        return True
    if _FOLLOWUP_HINT_RE.search(text):
        return True
    if _DIALOG_REFERENCE_RE.search(text):
        return True
    return len(text) < SHORT_FOLLOWUP_MAX_LEN


def _message_text(msg: ChatMessage) -> str:
    text = (msg.content or "").strip()
    if text:
        return text
    media_refs = msg.media_refs
    if not media_refs or not isinstance(media_refs, dict):
        return ""
    part = media_refs.get("part")
    if not part or part.get("type") != "text":
        return ""
    part_text = (part.get("text") or "").strip()
    if part_text.startswith(_VOICE_PREFIX):
        return part_text[len(_VOICE_PREFIX) :].lstrip("\n").strip()
    return part_text


def recent_dialog_summary(
    history: list[ChatMessage],
    *,
    limit: int = 4,
    roles: set[str] | None = None,
    user_max_chars: int = 400,
    assistant_max_chars: int = 400,
) -> str:
    """Краткий контекст последних реплик для RAG-поиска / агентов.

    roles — если задан, берём только эти роли (напр. {"user"} при явной правке,
    чтобы ошибочный ответ ассистента не отравлял condense/поиск).
    Для agent write/answer поднимай assistant_max_chars — иначе JSON-контракты
    из прошлых ответов обрезаются и kits выдумывают короткий stub.
    """
    lines: list[str] = []
    # Идём с конца, чтобы «последние N подходящих» — именно свежие, а не первые N.
    for msg in reversed(history):
        if roles is not None and msg.role not in roles:
            continue
        text = _message_text(msg)
        if not text:
            continue
        role = "Пользователь" if msg.role == "user" else "Ассистент"
        cap = assistant_max_chars if msg.role == "assistant" else user_max_chars
        lines.append(f"{role}: {text[:cap]}")
        if len(lines) >= limit:
            break
    lines.reverse()
    return "\n".join(lines)


def recent_dialog_summary_for_agents(history: list[ChatMessage]) -> str:
    """История для LangGraph: сохраняем полные контракты из прошлых ответов."""
    return recent_dialog_summary(
        history,
        limit=8,
        user_max_chars=1_200,
        assistant_max_chars=8_000,
    )


CONDENSE_SYSTEM_PROMPT = (
    "Ты переписываешь последний вопрос пользователя в один самостоятельный "
    "поисковый запрос к базе знаний по продукту «История операций» (СберИнвестор). "
    "Подставь из контекста диалога пропущенную тему, если вопрос ссылается на "
    "предыдущие реплики (например, «приведи пример» → «пример JSON ответа с "
    "комиссиями от БПХ», «трансфер» → «формат ответа с комиссиями "
    "от БПХ в History Ops»). Сохраняй доменные термины и аббревиатуры как есть "
    "(БПХ, BPH, BC, DCA, Composite, History Ops, GET_OPERATIONS_WITH_DETAILS, "
    "GET_DETAILS, SEND_DETAILS и т.п.). "
    "Если последняя реплика ИСПРАВЛЯЕТ или отвергает предыдущий ответ "
    "(«нет, я имел в виду…», «не X, а Y», «это не то»), строй запрос вокруг "
    "НОВОГО термина из последней реплики и НЕ переноси отвергнутые термины из "
    "прежних реплик. Не добавляй термины, в которых не уверен, — лучше короткий "
    "точный запрос, чем длинный с сомнительными словами. "
    "Верни ТОЛЬКО переписанный запрос одной строкой на русском: без пояснений, "
    "без кавычек, без префиксов. Если вопрос уже самостоятельный — верни его без "
    "изменений."
)


def build_condense_messages(
    current: str,
    history: list[ChatMessage],
    *,
    limit: int = 6,
) -> list[dict] | None:
    """Messages для LLM-свёртки follow-up в самостоятельный запрос.

    None — когда сворачивать нечего (нет истории или текст пустой): вызывающий
    код тогда пропускает LLM-вызов и ищет по исходной реплике.

    При явной правке («это не то», «мне нужен…») в контекст попадают только
    реплики пользователя: иначе ошибочный ответ ассистента (напр. про Composite
    / SEND_OPERATIONS_FEED) отравляет свёртку и уводит retrieval не на тот слой.
    """
    current = (current or "").strip()
    if not current or not history:
        return None
    # При правке — только user (последняя + 1–2 предыдущих), без assistant.
    if is_follow_up_clarification(current):
        summary = recent_dialog_summary(
            history, limit=min(limit, 3), roles={"user"}
        )
    else:
        summary = recent_dialog_summary(history, limit=limit)
    if not summary:
        return None
    user = (
        f"Контекст диалога:\n{summary}\n\n"
        f"Последний вопрос пользователя: {current}\n\n"
        "Самостоятельный поисковый запрос:"
    )
    return [
        {"role": "system", "content": CONDENSE_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def sanitize_condensed(raw: str, *, fallback: str, max_len: int = 400) -> str:
    """Чистит ответ LLM-свёртки: одна строка, без кавычек/префиксов, с ограничением.

    Если LLM вернула мусор/пустоту — возвращаем исходную реплику (fallback),
    чтобы retrieval всё равно отработал.
    """
    text = (raw or "").strip()
    if not text:
        return fallback
    text = text.splitlines()[0].strip()
    prefixes = ("запрос:", "поисковый запрос:", "самостоятельный запрос:")
    # Кавычки и префикс могут идти в любом порядке ("Запрос: «...»" или "«Запрос: ...»"),
    # поэтому чистим по кругу, пока строка укорачивается.
    changed = True
    while changed:
        before = text
        text = text.strip("\"'«»`").strip()
        for prefix in prefixes:
            if text.lower().startswith(prefix):
                text = text[len(prefix) :].strip()
        changed = text != before
    if not text:
        return fallback
    return text[:max_len]


def _references_dialog(text: str) -> bool:
    return bool(_DIALOG_REFERENCE_RE.search(text or ""))


def _integration_layer_queries(current: str, history: list[ChatMessage]) -> list[str]:
    """Дополнительные запросы под нужный слой интеграции."""
    blob = f"{current}\n{recent_dialog_summary(history, limit=6)}"
    extras: list[str] = []

    if _HO_TO_COMPOSITE_RE.search(blob):
        terms = "GET_DETAILS SEND_DETAILS gRPC proto HistoryOps Composite funds_output"
        if _FRONTEND_LAYER_RE.search(blob):
            terms += " не screenData sections"
        extras.append(f"{current} {terms}")

    if _BPH_LAYER_RE.search(blob):
        extras.append(f"{current} GET_OPERATIONS_WITH_DETAILS BPH lead details funds_output")

    if _MAPPING_RE.search(blob):
        extras.append(
            f"{current} маппинг operation_type BPH Composite tax TAX_RETAIN funds_output"
        )

    return extras


def build_rag_queries(
    current: str,
    *,
    history: list[ChatMessage] | None = None,
    max_queries: int = 4,
) -> list[str]:
    """Один или несколько запросов для retrieval с учётом follow-up."""
    current = (current or "").strip()
    if not current:
        return []

    history = history or []
    queries: list[str] = [current]

    is_clarification = is_follow_up_clarification(current)
    needs_context = is_clarification or (
        _references_dialog(current) and len(current) < 240
    )

    if history and (
        is_clarification
        or _references_dialog(current)
        or _MAPPING_RE.search(current)
    ):
        for extra in _integration_layer_queries(current, history):
            if extra not in queries:
                queries.append(extra)

    if needs_context and history:
        summary = recent_dialog_summary(history, limit=4)
        if summary:
            contextual = f"{current}\n\nКонтекст диалога:\n{summary}"
            if contextual not in queries:
                queries.append(contextual)

    return queries[:max_queries]
