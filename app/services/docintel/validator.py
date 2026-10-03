"""Validate-агент: независимый review + жёсткая (не-LLM) сверка с Qdrant.

Мягкий LLM-review правит черновик; затем ``check_json_grounded`` режет
самодельный JSON, который модель могла «ок»нуть. Пропуск = только то,
что структурно опирается на evidence из Qdrant.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from app.services.docintel.client import ToolCallClient
from app.services.docintel.grounding import (
    check_json_grounded,
    evidence_excerpt_answer,
    extract_json_objects,
    gap_refusal_text,
)

log = logging.getLogger(__name__)

_EVIDENCE_LIMIT = 32_000
_DRAFT_LIMIT = 60_000
_BRIEF_LIMIT = 4_000
_MAX_QUERIES = 6

_TOY_CONTRACT_RE = re.compile(
    r'("param1"|\bparam1\b|"result"\s*:\s*\[|"status"\s*:\s*"SUCCESS"|"item1")',
    re.IGNORECASE,
)

_THIN_REFUSAL_RE = re.compile(
    r"(?i)\bотказ\b|не\s+наш[её]л|нет\s+примера|в\s+kb\s+нет|"
    r"в\s+базе\s+знаний.{0,40}нет|не\s+могу\s+(ответить|найти)|"
    r"ничего\s+не\s+наш"
)

_SYSTEM_DOCUMENT = (
    "Ты validate_agent DocIntel — независимый ревьюер ВСЕГО документа фичи.\n"
    "Источник истины — ТОЛЬКО запрос пользователя + фрагменты RAG (Qdrant) ниже. "
    "Вне Qdrant факты запрещены.\n"
    "\n"
    "Проверь и исправь ВЕСЬ черновик целиком:\n"
    "- цель / бизнес-требования / ограничения;\n"
    "- use case AS IS / TO BE;\n"
    "- интеграции: request/response, таблицы, JSON — копируй структуру из RAG;\n"
    "- модель данных / NFR / observability — только по RAG.\n"
    "\n"
    "Правила:\n"
    "1) Целевые обмены/API — из ЗАПРОСА. Чужой контракт из RAG не подсовывай.\n"
    "2) Нельзя придумывать поля, обёртки, статусы, типы. Нет в Qdrant → GAP-*.\n"
    "3) «Похожий» самодельный JSON (другие root/поля) = ошибка, замени по RAG "
    "или пометь GAP.\n"
    "4) Не выкидывай структуру документа; правь содержание.\n"
    "5) Запрещены учебные stub (param1, урезанный `{operations:[...]}`).\n"
    "\n"
    "Верни ТОЛЬКО полный исправленный Markdown. Без преамбулы и ```markdown."
)

_SYSTEM_ANSWER = (
    "Ты validate_agent DocIntel — ревьюер короткого ответа (не документа фичи).\n"
    "Источник истины — ЗАПРОС + RAG (Qdrant) ниже. Диалог/прошлые ответы "
    "в evidence не считаются документацией. Придумывать запрещено.\n"
    "\n"
    "1) JSON/поля черновика ОБЯЗАНЫ совпадать со структурой примера из RAG "
    "(те же root-ключи и вложенность). Иначе перепиши: скопируй JSON из RAG.\n"
    "2) «Похожий» самодельный JSON (другие имена, статусы, обёртки вроде "
    "screenData вместо documented root) = ошибка, не оставляй.\n"
    "3) Нет нужного примера в RAG — честный отказ одной фразой, без выдумки.\n"
    "4) Не раздувай в полный документ фичи.\n"
    "5) Не возвращай черновик как есть, если он расходится с RAG.\n"
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


def _is_thin_refusal(text: str) -> bool:
    """Короткий «отказался», хотя вопрос был про пример/контракт."""
    t = (text or "").strip()
    if not t or len(t) > 700:
        return False
    return bool(_THIN_REFUSAL_RE.search(t))


def _evidence_usable(evidence: str) -> bool:
    """В Qdrant реально есть материал (JSON / таблицы / длинный контекст)."""
    ev = (evidence or "").strip()
    if len(ev) < 1200:
        return False
    if extract_json_objects(ev):
        return True
    if ev.count("|") >= 8:
        return True
    return len(ev) >= 3500


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
    """Запросы в Qdrant: формулировки из брифа пользователя, без спецкейсов."""
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


def _prefer_tokens_for_brief(brief: str) -> tuple[str, ...]:
    b = (brief or "").lower()
    if re.search(r"get[_\s-]*linked|linked\s*events|linkedin|linkedevents", b):
        return ("linkedevents", "condtradeorder", "tradeorder", "agreement")
    if re.search(r"screendata|композит|деталка|лент", b):
        return ("screendata", "operationtype", "sections", "varmargin")
    return ("linkedevents", "screendata", "varmargin", "operations")


def _hard_ground_or_reject(
    text: str,
    evidence: str,
    *,
    mode: Literal["document", "answer"],
    brief: str = "",
) -> str:
    """Механический фильтр: неподтверждённый / чужой-обмен JSON не проходит."""
    ok, reason = check_json_grounded(text, evidence, brief=brief)
    if ok:
        log.info("validate_hard_ground: PASS mode=%s %s", mode, reason)
        return text

    log.warning("validate_hard_ground: FAIL mode=%s %s", mode, reason)
    print(
        f"  → validate_agent: HARD FAIL grounding ({reason})",
        flush=True,
    )
    if mode == "answer" and _evidence_usable(evidence):
        # Чужой слой (screenData вместо linkedEvents) — отдать выдержки нужного контракта.
        fallback = evidence_excerpt_answer(
            evidence,
            prefer_tokens=_prefer_tokens_for_brief(brief),
        )
        if fallback and not _is_thin_refusal(fallback):
            log.warning(
                "validate_hard_ground: evidence fallback after %s chars=%d",
                reason,
                len(fallback),
            )
            return fallback
    if mode == "answer":
        return gap_refusal_text()
    return (
        "# GAP: контракт не подтверждён Qdrant\n\n"
        f"Жёсткая проверка структуры JSON/контракта провалена (`{reason}`).\n"
        "Документ не принят: нельзя публиковать request/response, выдуманные "
        "вне фрагментов базы знаний (Qdrant).\n"
        "Дополни корпус или уточни brief — затем перегенерируй.\n"
    )


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
    """Сверить draft с Qdrant и вернуть только grounded текст.

    После LLM всегда жёсткая проверка JSON↔Qdrant. Провал → GAP/отказ,
    а не «оставить черновик».
    """
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
        log.warning("validate_agent: нет evidence — hard-check на пустом KB")
        return _hard_ground_or_reject(
            draft, "", mode=mode, brief=feature_brief
        )

    # Ранний hard-fail: если draft уже выдуман — скажем LLM явно.
    draft_ok, draft_reason = check_json_grounded(
        draft, evidence, brief=feature_brief
    )
    if not draft_ok:
        log.warning(
            "validate_agent: draft уже ungrounded (%s) — LLM должен переписать",
            draft_reason,
        )

    if mode == "answer":
        flags: list[str] = [
            "Источник истины — только запрос + RAG (Qdrant) ниже. Придумывать запрещено.",
            "JSON/поля черновика должны совпадать со структурой примера RAG "
            "(те же root-ключи); иначе перепиши по RAG целиком или отказ.",
            "Самодельный «похожий» JSON — ошибка.",
            "Нет примера в RAG — честный отказ.",
        ]
    else:
        flags = [
            "Проверь весь документ по запросу и RAG (Qdrant) ниже.",
            "Нельзя придумывать контракты/JSON вне RAG — только GAP-*.",
            "Чужой обмен/API вместо запрошенного — ошибка, исправь по RAG.",
        ]
    if _needs_contract_fix(draft):
        flags.append("В черновике учебные заглушки контракта — замени по RAG.")
    if not draft_ok:
        flags.append(
            f"КРИТИЧНО (автопроверка): черновик не проходит сверку с Qdrant "
            f"({draft_reason}). Перепиши JSON дословно по структуре из RAG "
            f"или верни отказ/GAP — не оставляй самодельный контракт."
        )

    draft_label = (
        "Черновик ответа (исправь целиком)"
        if mode == "answer"
        else "Черновик документа (исправь целиком — все разделы)"
    )

    def _build_user_content(extra_flags: list[str] | None = None) -> str:
        all_flags = flags + (extra_flags or [])
        return (
            "## Обязательные замечания\n"
            + "\n".join(f"- {f}" for f in all_flags)
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

    async def _call(user_content: str) -> str:
        response = await client._create_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
        )
        return _strip_fence(response.choices[0].message.content or "")

    fixed = await _call(_build_user_content())
    candidate = draft
    if not fixed:
        log.warning("validate_agent: пустой ответ модели — беру draft → hard-check")
    else:
        min_ratio = 0.35 if mode == "answer" else 0.45
        min_abs = 80 if mode == "answer" else 400
        if len(fixed) < max(min_abs, int(len(draft) * min_ratio)):
            log.warning(
                "validate_agent: ответ слишком короткий (%d vs draft %d mode=%s) "
                "— беру draft → hard-check",
                len(fixed),
                len(draft),
                mode,
            )
        else:
            candidate = fixed

    # Soft-LLM часто «ок» на выдуманном JSON. Retry, затем hard gate.
    if mode == "answer" and candidate.strip() == draft.strip() and not draft_ok:
        log.warning(
            "validate_agent: answer unchanged и ungrounded — retry",
        )
        retry = await _call(
            _build_user_content(
                [
                    "КРИТИЧНО: прошлый проход вернул черновик без изменений. "
                    "Автопроверка структуры JSON провалена. "
                    "Либо скопируй JSON/таблицы из RAG ниже дословно по структуре, "
                    "либо честный отказ. Самодельный JSON запрещён.",
                ]
            )
        )
        if retry and len(retry) >= max(80, int(len(draft) * 0.35)):
            candidate = retry

    # Ещё один проход, если после LLM всё ещё ungrounded.
    ok_after, reason_after = check_json_grounded(
        candidate, evidence, brief=feature_brief
    )
    if not ok_after and candidate.strip() != draft.strip():
        # candidate уже другой, но всё равно плохой — последний retry
        log.warning(
            "validate_agent: после LLM всё ещё ungrounded (%s) — last retry",
            reason_after,
        )
        retry2 = await _call(
            _build_user_content(
                [
                    f"Автопроверка снова FAIL ({reason_after}). "
                    "Верни отказ или JSON, скопированный из RAG. "
                    "Любая новая структура полей запрещена.",
                ]
            )
        )
        if retry2 and len(retry2) >= 40:
            candidate = retry2

    # Ложный отказ при живом Qdrant: LLM retry, иначе механические выдержки.
    if (
        mode == "answer"
        and _is_thin_refusal(candidate)
        and _evidence_usable(evidence)
    ):
        log.warning(
            "validate_agent: thin refusal при usable evidence (%d chars) — retry",
            len(evidence),
        )
        retry_refuse = await _call(
            _build_user_content(
                [
                    "КРИТИЧНО: в блоке RAG (Qdrant) ЕСТЬ таблицы и/или JSON по теме. "
                    "Короткий отказ недопустим. Перепиши ответ: скопируй из RAG "
                    "релевантные таблицы маппинга и/или пример JSON (структура "
                    "дословно). Опечатка в запросе не повод отказывать.",
                ]
            )
        )
        if (
            retry_refuse
            and len(retry_refuse) >= 80
            and not _is_thin_refusal(retry_refuse)
        ):
            candidate = retry_refuse
        else:
            candidate = evidence_excerpt_answer(evidence)
            log.warning(
                "validate_agent: MECHANICAL evidence fallback chars=%d",
                len(candidate),
            )
            print(
                "  → validate_agent: LLM отказался при живом Qdrant — "
                "отдаю выдержки из evidence",
                flush=True,
            )

    grounded = _hard_ground_or_reject(
        candidate, evidence, mode=mode, brief=feature_brief
    )
    log.info(
        "validate_agent: done mode=%s draft_chars=%d out_chars=%d evidence_chars=%d",
        mode,
        len(draft),
        len(grounded),
        len(evidence),
    )
    return grounded
