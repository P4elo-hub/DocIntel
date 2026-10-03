"""Validate-агент: независимый LLM-review черновика по RAG (Qdrant).

Мягкий review: сверяет факты с evidence и правит черновик.
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
_MAX_QUERIES = 6

_TOY_CONTRACT_RE = re.compile(
    r'("param1"|\bparam1\b|"result"\s*:\s*\[|"status"\s*:\s*"SUCCESS"|"item1")',
    re.IGNORECASE,
)

_SYSTEM_DOCUMENT = (
    "Ты validate_agent DocIntel — независимый ревьюер ВСЕГО документа фичи.\n"
    "Источник истины — ТОЛЬКО запрос пользователя + фрагменты RAG (Qdrant) ниже. "
    "Вне Qdrant факты запрещены.\n"
    "\n"
    "Проверь и исправь ВЕСЬ черновик целиком:\n"
    "- цель / бизнес-требования / ограничения;\n"
    "- use case AS IS / TO BE;\n"
    "- интеграции: request/response, таблицы, JSON — по RAG;\n"
    "- модель данных / NFR / observability — только по RAG.\n"
    "\n"
    "Правила:\n"
    "1) Целевые обмены/API — из ЗАПРОСА. Чужой контракт из RAG не подсовывай.\n"
    "2) Нельзя придумывать поля, обёртки, статусы, типы. Нет в Qdrant → GAP-*.\n"
    "3) Не выкидывай структуру документа; правь содержание.\n"
    "4) Запрещены учебные stub (param1, урезанный `{operations:[...]}`).\n"
    "\n"
    "Верни ТОЛЬКО полный исправленный Markdown. Без преамбулы и ```markdown."
)

_SYSTEM_ANSWER = (
    "Ты validate_agent DocIntel — независимый ревьюер ответа.\n"
    "Источник истины — ЗАПРОС + RAG (Qdrant) ниже.\n"
    "Исправь фактические ошибки относительно RAG. "
    "Если вопрос про обмен/процесс/формат — убедись, что ответ это закрывает, "
    "а не только кидает JSON.\n"
    "Не раздувай ответ в полный документ фичи.\n"
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


def _extract_search_formulation(feature_brief: str) -> str:
    """Достаёт «поисковую формулировку» из brief validate_agent_node, если есть."""
    text = feature_brief or ""
    m = re.search(
        r"поисковая формулировка:\s*(.+)$",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip().strip(")").strip().splitlines()[0][:240]
    return ""


def _build_review_queries(
    feature_brief: str,
    *,
    mode: Literal["document", "answer"] = "document",
) -> list[str]:
    """Запросы в Qdrant: формулировки из брифа пользователя."""
    brief = (feature_brief or "").strip()
    formulated = _extract_search_formulation(brief)
    original_line = brief.splitlines()[0].strip() if brief else ""
    queries: list[str] = []
    for q in (original_line, formulated, brief[:240]):
        q = (q or "").strip()
        if q and q not in queries:
            queries.append(q)
    if mode == "document" and original_line:
        queries.append(f"{original_line} параметры запроса ответа пример JSON")
    return queries[:_MAX_QUERIES]


async def collect_fresh_rag_evidence(
    feature_brief: str,
    *,
    mode: Literal["document", "answer"] = "document",
) -> str:
    """Свежий evidence из Qdrant для validate_agent."""
    from app.services.agent_graph import get_rag_service

    rag = get_rag_service()
    if rag is None:
        log.warning("validate_rag_evidence: RAGService/Qdrant не готов")
        return ""

    queries = _build_review_queries(feature_brief, mode=mode)
    if not queries:
        return ""

    try:
        result = await rag.retrieve_context_multi(queries, prioritize_first=True)
    except Exception:  # noqa: BLE001
        log.exception("validate_rag_evidence: Qdrant retrieve failed")
        return ""

    evidence = (result.get("context_str") or "").strip()
    if len(evidence) > _EVIDENCE_LIMIT:
        evidence = evidence[:_EVIDENCE_LIMIT] + (
            f"\n\n...[обрезано для review: {_EVIDENCE_LIMIT}]"
        )
    log.info(
        "validate_rag_evidence mode=%s queries=%d chars=%d confident=%s top_score=%s",
        mode,
        len(queries),
        len(evidence),
        result.get("confident"),
        result.get("top_score"),
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
    """Сверить draft с RAG через LLM и вернуть исправленный текст."""
    draft = (draft_answer or "").strip()
    if not draft:
        return draft

    print(
        f"  → validate_agent: независимый Qdrant-review (mode={mode})",
        flush=True,
    )

    pipeline_ctx = (search_context or "").strip()
    if mode == "answer" and pipeline_ctx:
        evidence = pipeline_ctx
        log.info(
            "validate_agent: evidence=search_context (Qdrant pipeline) chars=%d",
            len(evidence),
        )
    else:
        evidence = await collect_fresh_rag_evidence(feature_brief, mode=mode)
        if not evidence.strip():
            evidence = pipeline_ctx
            if evidence:
                log.warning(
                    "validate_agent: fresh Qdrant пуст — fallback на search_context"
                )
    if not evidence.strip():
        log.warning("validate_agent: нет evidence — оставляю draft")
        return draft

    if mode == "answer":
        flags: list[str] = [
            "Источник истины — запрос + RAG (Qdrant) ниже. Придумывать запрещено.",
            "Ответ должен закрывать вопрос пользователя (обмен/процесс/формат/"
            "пример — что спросили).",
            "JSON/поля — по структуре из RAG, без самодельных обёрток.",
        ]
    else:
        flags = [
            "Проверь весь документ по запросу и RAG (Qdrant) ниже.",
            "Нельзя придумывать контракты/JSON вне RAG — только GAP-*.",
            "Чужой обмен/API вместо запрошенного — ошибка, исправь по RAG.",
        ]
    if _needs_contract_fix(draft):
        flags.append("В черновике учебные заглушки контракта — замени по RAG.")

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
        "## RAG (Qdrant) — ИСТОЧНИК ИСТИНЫ\n"
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
            "validate_agent: ответ слишком короткий (%d vs draft %d mode=%s) "
            "— оставляю draft",
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
