"""Validate-агент: проверщик draft по KB (не второй автор).

Сверяет черновик с evidence (обычно search_context из retrieve).
Исправляет только фактические расхождения с KB; новое из запроса
пользователя не выкидывает. Нет расхождений → вернуть draft как есть.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from app.services.docintel.client import ToolCallClient
from app.services.docintel.kb_expand import (
    brief_wants_contract,
    contract_gap_answer,
    draft_claims_contract,
    evidence_covers_requested_apis,
    expand_search_context,
    fetch_lexical_contracts,
    requested_api_keys,
)

_FRONTEND_UI_JSON_RE = re.compile(
    r'"screenData"\s*:.*"sections"\s*:',
    re.IGNORECASE | re.DOTALL,
)
_INTEGRATION_GOWD_KEYS = frozenset(
    {"getoperationswithdetails", "getoperationwithdetails"}
)


def _draft_is_frontend_ui_for_integration_api(brief: str, draft: str) -> bool:
    """FE screenData/sections вместо интеграционного GetOperationsWithDetails."""
    if not (requested_api_keys(brief) & _INTEGRATION_GOWD_KEYS):
        return False
    if not _FRONTEND_UI_JSON_RE.search(draft or ""):
        return False
    # BE-контракт обычно про lead / funds_output, не про screenData.
    return not re.search(r'"lead"\s*:|funds_output', draft or "", re.I)
from app.tools.search_kb.handler import SearchKbHandler, extract_api_ids

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
    "Ты validate_agent DocIntel — ПРОВЕРЩИК документа фичи, не автор.\n"
    "Сверь черновик с запросом пользователя и KB ниже.\n"
    "\n"
    "Правила:\n"
    "1) Правь только фактические ошибки относительно KB "
    "(чужой обмен/JSON, выдуманные поля, stub вроде param1).\n"
    "2) Новые поля/таблицы/требования из ЗАПРОСА пользователя, которых ещё "
    "нет в KB — НЕ удаляй и не помечай ошибкой; это целевые изменения фичи.\n"
    "3) То, что уже описано в KB — должно совпадать с KB "
    "(имена полей, примеры, типы). Нет в KB полного контракта → GAP-*, "
    "не синтезируй JSON.\n"
    "4) Нет расхождений — верни черновик БЕЗ изменений.\n"
    "5) Не переписывай документ «с нуля» и не улучшай стиль без нужды.\n"
    "\n"
    "Верни ТОЛЬКО итоговый Markdown документа. Без преамбулы и ```markdown."
)

_SYSTEM_ANSWER = (
    "Ты validate_agent DocIntel — ПРОВЕРЩИК ответа, не автор.\n"
    "Сверь черновик с запросом пользователя и KB ниже.\n"
    "\n"
    "ЖЁСТКОЕ ПРАВИЛО СООТВЕТСТВИЯ ЗАПРОСУ:\n"
    "- Черновик должен отвечать РОВНО на запрошенный обмен/API/таблицу/"
    "слой. Чужой обмен или фронтовый screenData/sections вместо "
    "интеграционного контракта — ошибка: замени на фрагмент из KB по "
    "нужному обмену или честный отказ, если в KB его нет.\n"
    "- Не оставляй JSON другого обмена, слоя или другого типа операции.\n"
    "\n"
    "Правила:\n"
    "1) Правь факты, которые противоречат KB или запросу "
    "(не тот обмен, поля не из контракта).\n"
    "2) JSON/пример — только дословный фрагмент запрошенного типа из KB. "
    "Нет такого примера → честный отказ. Собранный по маппингу или по "
    "аналогии JSON, lead: null, details: null и чужой тип в каркасе — "
    "замени на отказ. Таблицу маппинга можно оставить цитатой, не JSON.\n"
    "3) Нет расхождений с KB и запросом — верни черновик БЕЗ изменений.\n"
    "4) Не раздувай ответ в документ фичи и не переписывай без нужды.\n"
    "\n"
    "Верни ТОЛЬКО итоговый Markdown. Без преамбулы и ```markdown."
)


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


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
    """Запросы на дочитывание контракта, если pipeline evidence пуст/тощий."""
    brief = (feature_brief or "").strip()
    formulated = _extract_search_formulation(brief)
    original_line = brief.splitlines()[0].strip() if brief else ""
    queries: list[str] = []
    for q in (original_line, formulated, brief[:240]):
        q = (q or "").strip()
        if q and q not in queries:
            queries.append(q)
    for api_id in extract_api_ids(brief)[:4]:
        api_q = f"{api_id} параметры запроса ответа пример JSON"
        if api_q not in queries:
            queries.append(api_q)
    if mode == "document" and original_line:
        queries.append(f"{original_line} параметры запроса ответа пример JSON")
    return queries[:_MAX_QUERIES]


async def collect_fresh_rag_evidence(
    feature_brief: str,
    *,
    mode: Literal["document", "answer"] = "document",
) -> str:
    """Свежий evidence из Qdrant — только fallback, если pipeline пуст."""
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


def _resolve_kb_handler(kb_handler: SearchKbHandler | None) -> SearchKbHandler | None:
    if kb_handler is not None:
        return kb_handler
    try:
        from app.services.agent_graph import _rag_kb_handler

        return _rag_kb_handler()
    except Exception:  # noqa: BLE001
        log.exception("validate: rag kb handler unavailable")
        return None


async def _collect_evidence(
    feature_brief: str,
    search_context: str,
    *,
    mode: Literal["document", "answer"],
    kb_handler: SearchKbHandler | None,
) -> str:
    """Evidence для сверки: сначала pipeline search_context, без лишнего перепоиска."""
    pipeline_ctx = (search_context or "").strip()
    kb = _resolve_kb_handler(kb_handler)
    queries = _build_review_queries(feature_brief, mode=mode)

    if pipeline_ctx:
        log.info(
            "validate_agent: evidence=pipeline search_context chars=%d mode=%s",
            len(pipeline_ctx),
            mode,
        )
        # Дочитать lexical, если просят контракт, а нужного обмена в pipeline нет.
        if (
            kb is not None
            and brief_wants_contract(feature_brief)
            and not evidence_covers_requested_apis(pipeline_ctx, feature_brief)
        ):
            expanded = expand_search_context(
                kb,
                query=feature_brief,
                rag_context=pipeline_ctx,
                extra_queries=queries,
            )
            if expanded.strip() and evidence_covers_requested_apis(
                expanded, feature_brief
            ):
                log.info("validate_agent: lexical fill on top of pipeline context")
                return expanded
        return pipeline_ctx

    # Pipeline пуст — fallback: свежий Qdrant + lexical.
    base = await collect_fresh_rag_evidence(feature_brief, mode=mode)
    if kb is None:
        return base
    expanded = expand_search_context(
        kb,
        query=feature_brief,
        rag_context=base,
        extra_queries=queries,
    )
    return expanded.strip() or base


async def validate_against_kb(
    client: ToolCallClient,
    *,
    feature_brief: str,
    search_context: str,
    draft_answer: str,
    mode: Literal["document", "answer"] = "document",
    kb_handler: SearchKbHandler | None = None,
) -> str:
    """Проверить draft по KB; править только расхождения, иначе вернуть draft."""
    draft = (draft_answer or "").strip()
    if not draft:
        return draft

    print(
        f"  → validate_agent: review draft vs KB (mode={mode})",
        flush=True,
    )

    evidence = await _collect_evidence(
        feature_brief,
        search_context,
        mode=mode,
        kb_handler=kb_handler,
    )

    wants = brief_wants_contract(feature_brief) or draft_claims_contract(draft)
    # «Есть JSON» недостаточно: нужен контракт именно запрошенного обмена.
    has_contract = evidence_covers_requested_apis(evidence, feature_brief)

    if wants and not has_contract:
        kb = _resolve_kb_handler(kb_handler)
        if kb is not None:
            retry = fetch_lexical_contracts(kb, feature_brief)
            if retry and evidence_covers_requested_apis(retry, feature_brief):
                evidence = expand_search_context(
                    kb, query=feature_brief, rag_context=evidence or ""
                ) or retry
                has_contract = True
                log.info("validate_agent: lexical retry filled contract evidence")

    if wants and not has_contract and mode == "answer":
        log.warning(
            "validate_agent: no contract evidence — honest GAP (apis=%s)",
            extract_api_ids(feature_brief)[:4],
        )
        return contract_gap_answer(feature_brief)

    if not evidence.strip():
        log.warning("validate_agent: нет evidence — оставляю draft")
        return draft

    if mode == "answer":
        flags: list[str] = [
            "Ты проверщик: правь только ошибки относительно KB.",
            "Нет расхождений — верни черновик без изменений.",
            "JSON/поля — только дословный пример запрошенного типа из KB. "
            "Нет такого примера → честный отказ, не собранный JSON и не "
            "чужой пример.",
            "Не раздувай ответ и не переписывай стиль без нужды.",
        ]
        if _draft_is_frontend_ui_for_integration_api(feature_brief, draft):
            flags.append(
                "КРИТИЧНО: в запросе интеграционный GetOperationsWithDetails/"
                "GET_OPERATIONS_WITH_DETAILS, а черновик — фронтовый "
                "screenData/sections. Замени JSON на контракт этого обмена из "
                "секции «Контракты из файлов KB» (lead/BPH), иначе честный отказ. "
                "Фронтовый JSON оставлять нельзя."
            )
    else:
        flags = [
            "Ты проверщик документа: правь только ошибки относительно KB.",
            "Новые поля/требования из запроса пользователя не удаляй.",
            "Нет расхождений — верни черновик без изменений.",
            "Нет полного контракта в KB — GAP-*, не синтезируй JSON.",
            "Чужой обмен/API вместо запрошенного — исправь по KB.",
        ]
    if _needs_contract_fix(draft):
        flags.append("В черновике учебные заглушки контракта — замени по KB или GAP.")

    draft_label = (
        "Черновик ответа"
        if mode == "answer"
        else "Черновик документа"
    )
    user_content = (
        "## Обязательные замечания\n"
        + "\n".join(f"- {f}" for f in flags)
        + "\n\n"
        "## Запрос пользователя\n"
        f"{feature_brief.strip()[:_BRIEF_LIMIT]}\n\n"
        "## KB — эталон для сверки\n"
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

    # Модель снова нарисовала JSON при отсутствии контракта в evidence — GAP.
    if (
        mode == "answer"
        and wants
        and not has_contract
        and draft_claims_contract(fixed)
    ):
        log.warning("validate_agent: model invented JSON without evidence — GAP")
        return contract_gap_answer(feature_brief)

    # Промпт не помог: всё ещё FE screenData при вопросе про GOWD → отдать lexical.
    if mode == "answer" and _draft_is_frontend_ui_for_integration_api(
        feature_brief, fixed
    ):
        lex_marker = "## Контракты из файлов KB"
        if lex_marker in evidence:
            lex_body = evidence.split(lex_marker, 1)[1]
            lex_body = lex_body.split("## RAG (Qdrant)", 1)[0].strip()
            if lex_body:
                log.warning(
                    "validate_agent: FE screenData for GOWD — replace with lexical KB"
                )
                return (
                    "По интеграционному обмену GetOperationsWithDetails / "
                    "GET_OPERATIONS_WITH_DETAILS (не фронтовый screenData):\n\n"
                    f"{lex_body[:12_000]}"
                )
        log.warning("validate_agent: FE screenData for GOWD without lexical — GAP")
        return contract_gap_answer(feature_brief)

    # Отката по длине нет: короткий фикс (выброшен чужой JSON) — валидный результат.
    log.info(
        "validate_agent: ok mode=%s draft_chars=%d fixed_chars=%d evidence_chars=%d "
        "has_contract=%s",
        mode,
        len(draft),
        len(fixed),
        len(evidence),
        has_contract,
    )
    return fixed
