"""Answer-агент: формулирует ответ по KB (не полный документ фичи).

Сценарий: classify → search → answer → validate.
Вход: user_request + search_context. Выход: draft_answer (Markdown).
"""

from __future__ import annotations

import logging

from app.services.docintel.client import ToolCallClient

log = logging.getLogger(__name__)

_KB_LIMIT = 18_000
_Q_LIMIT = 4_000

_SYSTEM = (
    "Ты answer_agent DocIntel. По запросу пользователя, контексту диалога и "
    "фрагментам KB (search_context) сформулируй точный ответ на русском.\n"
    "\n"
    "Правила:\n"
    "- Опирайся на search_context, запрос и контекст диалога "
    "(если ссылаются на прошлый пример/сообщение — бери его из диалога).\n"
    "- Если просят показать ту же операцию в другом формате обмена — "
    "трансформируй поля по правилам из KB, не выкидывай данные из примера диалога.\n"
    "- Если просят пример request/response — скопируй JSON/таблицы из KB "
    "целиком (все поля), не сокращай и не подменяй учебным REST-скелетом.\n"
    "- Не выдумывай поля, endpoint, коды ошибок.\n"
    "- Если в KB нет ответа — так и скажи, предложи уточнить запрос.\n"
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
    """Сформулировать ответ на вопрос по артефакту поиска (+ история чата)."""
    kb = (search_context or "").strip()
    question = (user_request or "").strip()
    history = (chat_history or "").strip()
    if not question:
        return ""

    parts = [
        "## Запрос пользователя\n",
        f"{question[:_Q_LIMIT]}\n\n",
    ]
    if history:
        parts.extend([
            "## Контекст диалога (если спрашивают про «данное сообщение» / прошлый пример — бери отсюда)\n",
            f"{history[:8000]}\n\n",
        ])
    parts.extend([
        "## search_context (KB)\n",
        f"{kb[:_KB_LIMIT] if kb else '_(пусто — поиск ничего не вернул)_'}\n",
    ])
    user_content = "".join(parts)

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
