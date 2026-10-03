"""Answer-агент: формулирует ответ строго по KB из Qdrant.

Сценарий: classify → retrieve_rag → answer → validate.
Вход: user_request + search_context (Qdrant). Выход: draft_answer (Markdown).
Придумывать контракты/JSON нельзя — только копирование структуры из KB.
"""

from __future__ import annotations

import logging
import re

from app.services.docintel.client import ToolCallClient
from app.services.docintel.grounding import evidence_excerpt_answer

log = logging.getLogger(__name__)

_THIN_REFUSAL_RE = re.compile(
    r"(?i)\bотказ\b|не\s+наш[её]л|нет\s+примера|в\s+kb\s+нет|"
    r"в\s+базе\s+знаний.{0,40}нет"
)

_KB_LIMIT = 18_000
_Q_LIMIT = 4_000

_SYSTEM = (
    "Ты answer_agent DocIntel. Ответь на русском СТРОГО по запросу и KB (Qdrant).\n"
    "\n"
    "ЖЁСТКИЕ ПРАВИЛА (нарушение = брак):\n"
    "1) Единственный источник фактов, полей, JSON, статусов, таблиц — блок KB "
    "(Qdrant) в user-сообщении. Общие знания модели и «логичные» догадки запрещены.\n"
    "2) Пример JSON/контракта — копируй структуру из KB: те же root-ключи, "
    "вложенность, имена полей. Не синтезируй «похожий» JSON "
    "(другие обёртки, status/type, списки).\n"
    "3) Целевой обмен/API/слой — только из ТЕКУЩЕГО запроса. Если в KB другой "
    "обмен — не подменяй им ответ.\n"
    "4) Диалог — только чтобы понять правку («не то»). Прошлый ответ в диалоге "
    "НЕ источник контракта.\n"
    "5) Отказ допустим ТОЛЬКО если в KB реально нет таблиц/JSON/описания по теме. "
    "Если в KB есть маппинг или пример (в т.ч. varmargin / «Вариационная маржа») — "
    "отвечай по нему: копируй таблицы и JSON. Опечатка в запросе "
    "(«в рационной» ≈ «вариационной») — не повод для отказа.\n"
    "6) Запрещено отвечать «Отказ / нет примера», когда блок KB ниже непустой "
    "и содержит релевантные таблицы или JSON — тогда обязан ответить по KB.\n"
    "7) Markdown без преамбулы «Вот ответ» и без обёртки ```markdown."
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
    """Сформулировать ответ на вопрос по артефакту Qdrant (+ история чата)."""
    kb = (search_context or "").strip()
    question = (user_request or "").strip()
    history = (chat_history or "").strip()
    if not question:
        return ""

    parts = [
        "## Запрос пользователя (обязательные ограничения)\n",
        f"{question[:_Q_LIMIT]}\n\n",
        "Ответ СТРОГО под этот запрос: тот же тип операции и тот же слой/API. "
        "Если в KB другой тип — не используй его как ответ. "
        "Придумывать JSON/поля нельзя.\n\n",
    ]
    if history:
        parts.extend([
            "## Диалог (только смысл правки; НЕ копируй отсюда чужой контракт)\n",
            f"{history[:4_000]}\n\n",
        ])
    parts.extend([
        "## KB из Qdrant — ЕДИНСТВЕННЫЙ источник контракта/JSON\n",
        "Копируй структуру из фрагментов ниже. Нет примера → отказ, не выдумывай.\n\n",
        f"{kb[:_KB_LIMIT] if kb else '_(пусто — Qdrant ничего не вернул; отказ без JSON)_'}\n",
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
    # Не пропускаем «Отказ» при живом KB — validate тоже чинит, но здесь быстрее.
    if (
        kb
        and len(kb) >= 1200
        and text
        and len(text) < 700
        and _THIN_REFUSAL_RE.search(text)
    ):
        log.warning(
            "answer_agent: thin refusal при kb_chars=%d — mechanical fallback",
            len(kb),
        )
        text = evidence_excerpt_answer(kb)
    log.info("answer_agent: chars=%d kb_chars=%d", len(text), len(kb))
    return text
