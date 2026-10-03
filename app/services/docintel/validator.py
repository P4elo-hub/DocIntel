"""Validate-агент: независимый review всего документа/ответа по свежему RAG.

Не ограничивается интеграционными контрактами: сверяет цель, use case, схему,
NFR, observability и любые факты в черновике с аналитикой в базе знаний.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from app.services.docintel.client import ToolCallClient

log = logging.getLogger(__name__)

_EVIDENCE_LIMIT = 32_000
_DRAFT_LIMIT = 60_000
_BRIEF_LIMIT = 4_000
_MAX_QUERIES = 8
_HIT_PER_QUERY = 7_000

_TOY_CONTRACT_RE = re.compile(
    r'("param1"|\bparam1\b|"result"\s*:\s*\[|"status"\s*:\s*"SUCCESS"|"item1")',
    re.IGNORECASE,
)

_SYSTEM_DOCUMENT = (
    "Ты validate_agent DocIntel — независимый ревьюер ВСЕГО документа фичи.\n"
    "Источник истины — СВЕЖИЕ фрагменты RAG (аналитика/KB) ниже. "
    "Не опирайся на search_context write-агента.\n"
    "\n"
    "Проверь и исправь ВЕСЬ черновик целиком, а не только интеграции:\n"
    "- цель / бизнес-требования / ограничения;\n"
    "- use case AS IS / TO BE (акторы, шаги, ветвления) — по фактам из RAG;\n"
    "- интеграции: request/response, таблицы полей, примеры JSON — как в RAG;\n"
    "- модель данных / схемы, если есть;\n"
    "- NFR, логирование, мониторинг, настройки — только то, что подтверждено RAG;\n"
    "- любые имена обменов, сервисов, полей, статусов, лимитов.\n"
    "\n"
    "Правила:\n"
    "1) Факты в документе должны соответствовать RAG. Противоречие → исправь "
    "по RAG или пометь GAP, если в RAG нет данных.\n"
    "2) Не выкидывай разделы и структуру документа; правь содержание.\n"
    "3) Новое из брифа оставляй; остальное без evidence из RAG не выдумывай.\n"
    "4) Запрещены учебные stub (param1, result+status+timestamp, урезанный "
    "`{operations:[...]}` вместо полного контракта из RAG).\n"
    "\n"
    "Верни ТОЛЬКО полный исправленный Markdown документа. "
    "Без преамбулы, без списка замечаний, без ```markdown."
)

_SYSTEM_ANSWER = (
    "Ты validate_agent DocIntel — независимый ревьюер ответа.\n"
    "Источник истины — СВЕЖИЕ фрагменты RAG ниже.\n"
    "Исправь любые фактические ошибки относительно аналитики в RAG "
    "(не только JSON-контракты). Не раздувай ответ в полный документ фичи.\n"
    "\n"
    "Верни ТОЛЬКО исправленный Markdown. Без преамбулы и ```markdown."
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


def _needs_contract_fix(draft: str) -> bool:
    return bool(_TOY_CONTRACT_RE.search(draft))


def _topic_seed(feature_brief: str, draft: str) -> str:
    """Короткая тема для тематических RAG-запросов."""
    line = (feature_brief or "").strip().splitlines()[0] if feature_brief.strip() else ""
    if not line:
        for raw in (draft or "").splitlines():
            if raw.startswith("#"):
                line = raw.lstrip("# ").strip()
                break
    return line[:160]


def _build_review_queries(feature_brief: str, draft: str) -> list[str]:
    """Набор RAG-запросов на весь документ: API + процесс + NFR + данные."""
    from app.tools.search_kb.handler import extract_api_ids

    blob = f"{feature_brief}\n{draft}"
    apis = extract_api_ids(blob)
    topic = _topic_seed(feature_brief, draft)
    queries: list[str] = []

    for api in apis[:4]:
        queries.append(f"{api} параметры запроса ответа пример JSON контракт")

    if topic:
        queries.extend([
            f"{topic} цель бизнес-требования процесс AS IS TO BE",
            f"{topic} use case сценарий акторы шаги",
            f"{topic} NFR производительность надёжность логирование мониторинг",
            f"{topic} модель данных схема поля",
        ])

    # Дедуп, лимит
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        key = q.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
        if len(unique) >= _MAX_QUERIES:
            break
    if not unique and topic:
        unique.append(topic)
    return unique


def _search_rag(query: str) -> str:
    """Прямой поиск по RAG + DocIntel docs."""
    from app.core.config import get_settings
    from app.tools.registry import ToolHandlers
    from app.tools.search_kb.handler import SearchKbHandler

    settings = get_settings()
    rag = SearchKbHandler(
        knowledge_base_path=None,
        docs_dir=settings.rag_data_dir,
    )
    docintel = ToolHandlers(
        knowledge_base_path=settings.docintel.knowledge_base_path,
        docs_dir=settings.docintel.docs_dir,
        methodology_dir=settings.docintel.methodology_dir,
        shablon_path=settings.docintel.shablon_path,
    )
    rag_hit = rag.search_kb(query)
    doc_hit = docintel.search_kb(query)
    parts: list[str] = []
    if rag_hit and "Ничего не найдено" not in rag_hit:
        parts.append(f"### RAG (`{settings.rag_data_dir}`)\n{rag_hit}")
    if doc_hit and "Ничего не найдено" not in doc_hit:
        parts.append(f"### DocIntel docs\n{doc_hit}")
    return "\n\n".join(parts)


def collect_fresh_rag_evidence(feature_brief: str, draft: str) -> str:
    """Свежий RAG по всей теме документа для validate_agent."""
    queries = _build_review_queries(feature_brief, draft)
    per_query = max(4_000, min(_HIT_PER_QUERY, _EVIDENCE_LIMIT // max(len(queries), 1)))
    blocks: list[str] = []
    total = 0
    for query in queries:
        hit = _search_rag(query)
        if not hit.strip():
            continue
        if len(hit) > per_query:
            hit = hit[:per_query] + f"\n\n...[обрезано для review: {len(hit)}]"
        block = f"## RAG query: {query}\n{hit}"
        if total + len(block) > _EVIDENCE_LIMIT and blocks:
            break
        blocks.append(block)
        total += len(block)
        log.info("validate_rag_query q=%r chars=%d", query[:120], len(hit))
    evidence = "\n\n".join(blocks)
    log.info(
        "validate_rag_evidence queries=%d chars=%d",
        len(blocks),
        len(evidence),
    )
    return evidence


async def validate_against_kb(
    client: ToolCallClient,
    *,
    feature_brief: str,
    search_context: str,
    draft_answer: str,
    mode: Literal["document", "answer"] = "document",
) -> str:
    """Сверить весь draft со свежим RAG и вернуть исправленный текст."""
    draft = (draft_answer or "").strip()
    if not draft:
        return draft

    print("  → validate_agent: независимый RAG-review всего документа", flush=True)
    evidence = collect_fresh_rag_evidence(feature_brief, draft)
    if not evidence.strip():
        evidence = (search_context or "").strip()
        log.warning("validate_agent: fresh RAG пуст — fallback на search_context")
    if not evidence.strip():
        log.warning("validate_agent: нет evidence — пропускаю правку")
        return draft

    flags: list[str] = [
        "Проверь ВЕСЬ документ/ответ: цель, use case, интеграции, данные, NFR — "
        "на соответствие RAG ниже.",
        "Источник истины — свежий RAG, не черновик write-агента.",
    ]
    if _needs_contract_fix(draft):
        flags.append(
            "В черновике учебные заглушки контракта — замени по RAG."
        )

    draft_label = (
        "Черновик ответа (исправь целиком)"
        if mode == "answer"
        else "Черновик документа (исправь целиком — все разделы)"
    )
    user_content = (
        "## Обязательные замечания\n"
        + "\n".join(f"- {f}" for f in flags)
        + "\n\n"
        "## Запрос пользователя\n"
        f"{feature_brief.strip()[:_BRIEF_LIMIT]}\n\n"
        "## Свежий RAG (аналитика / KB) — ИСТОЧНИК ИСТИНЫ\n"
        f"{evidence[:_EVIDENCE_LIMIT]}\n\n"
        f"## {draft_label}\n"
        f"{draft[:_DRAFT_LIMIT]}\n"
    )

    system = _SYSTEM_ANSWER if mode == "answer" else _SYSTEM_DOCUMENT
    max_tokens = max(client._max_tokens, 4096 if mode == "answer" else 8192)

    response = await client._create_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
    )
    fixed = _strip_fence(response.choices[0].message.content or "")
    if not fixed:
        log.warning("validate_agent: пустой ответ модели — оставляю draft")
        return draft

    min_ratio = 0.35 if mode == "answer" else 0.45
    min_abs = 80 if mode == "answer" else 400
    if len(fixed) < max(min_abs, int(len(draft) * min_ratio)):
        log.warning(
            "validate_agent: ответ слишком короткий (%d vs draft %d mode=%s) — оставляю draft",
            len(fixed),
            len(draft),
            mode,
        )
        return draft

    log.info(
        "validate_agent: ok mode=%s draft_chars=%d fixed_chars=%d evidence_chars=%d",
        mode,
        len(draft),
        len(fixed),
        len(evidence),
    )
    return fixed
