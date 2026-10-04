"""Answer-агент: формулирует ответ по KB (не полный документ фичи).

Сценарий: classify → retrieve_rag → answer → validate.
Вход: user_request + search_context.
История чата сюда не кладётся: classify/condense уже учли её в поисковом
запросе, retrieve собрал KB. Сырой диалог в промпте конкурировал с KB.
Выход: draft_answer (Markdown).
"""

from __future__ import annotations

import logging

from app.services.docintel.client import ToolCallClient

log = logging.getLogger(__name__)

_KB_LIMIT = 28_000
_Q_LIMIT = 4_000

_SYSTEM = (
    "Ты answer_agent DocIntel. Сформулируй точный ответ на русском.\n"
    "\n"
    "Входы:\n"
    "- Запрос пользователя — что нужно ответить сейчас "
    "(если есть «поисковая формулировка» — это тот же вопрос с учётом диалога).\n"
    "- search_context (KB) — единственный источник фактов, полей, JSON, "
    "endpoint, примеров.\n"
    "\n"
    "ЖЁСТКОЕ ПРАВИЛО СООТВЕТСТВИЯ ЗАПРОСУ (нарушать нельзя):\n"
    "- Отвечай ТОЛЬКО про тот объект, о котором спросили: интеграционный "
    "обмен/API, таблицу, сервис, слой (BPH/HO/Composite/фронт), экран.\n"
    "- Если спросили один обмен (напр. GET_OPERATIONS_WITH_DETAILS / "
    "GetOperationsWithDetails) — НЕ подставляй JSON, поля и примеры из "
    "другого обмена (SendOperations, SEND_OPERATIONS_FEED, ScreenApi, "
    "фронтовый screenData/sections и т.п.), даже если они есть в "
    "search_context рядом.\n"
    "- Если спросили одну таблицу/сущность — не отвечай данными другой.\n"
    "- Если в KB нет примера именно по запрошенному обмену/таблице — "
    "честно скажи, что в контексте нет нужного контракта. Не «спасай» "
    "ответ похожим JSON с другого слоя.\n"
    "\n"
    "Прочие правила:\n"
    "- Опирайся на search_context (сначала «Контракты из файлов KB», "
    "потом RAG), но только релевантные запросу фрагменты.\n"
    "- Пример request/response — копируй из KB целиком, не сокращай и "
    "не подменяй учебным скелетом.\n"
    "- Не выдумывай поля, endpoint, коды ошибок.\n"
    "- Ответ — Markdown без преамбулы «Вот ответ» и без обёртки ```markdown."
)


def _strip_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


async def write_answer_from_kb(
    client: ToolCallClient,
    *,
    user_request: str,
    search_context: str,
    chat_history: str = "",
) -> str:
    """Сформулировать ответ по запросу + search_context.

    ``chat_history`` оставлен в сигнатуре для совместимости вызовов и
    игнорируется: сырой диалог в answer не подаём.
    """
    del chat_history
    kb = (search_context or "").strip()
    question = (user_request or "").strip()
    if not question:
        return ""

    user_content = (
        "## Запрос пользователя\n"
        f"{question[:_Q_LIMIT]}\n\n"
        "## search_context (KB)\n"
        f"{kb[:_KB_LIMIT] if kb else '_(пусто — поиск ничего не вернул)_'}\n"
    )

    response = await client._create_completion(
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max(client._max_tokens, 4096),
    )
    text = _strip_fence(response.choices[0].message.content or "")
    log.info("answer_agent: chars=%d kb_chars=%d", len(text), len(kb))
    return text
