"""Lexical expand KB после Qdrant: контрактные секции целиком + grep/read.

Production answer/search раньше брал только dense-чанки Qdrant. Здесь
подмешиваем read-only lexical search_kb (API-id → request/response блоки),
чтобы JSON/таблицы не терялись на нарезке embeddings — но только если в
reranked RAG-контексте ещё нет контрактного тела (дыра в evidence).
"""

from __future__ import annotations

import logging
import re

from app.tools.search_kb.handler import (
    SearchKbHandler,
    _normalize_api_key,
    chunk_has_contract_body,
    extract_api_ids,
)

log = logging.getLogger(__name__)

_MAX_MERGED_CHARS = 36_000
# Lexical — довесок при дырке, не главная часть контекста.
_MAX_LEXICAL_GAP_CHARS = 12_000
_JSON_FENCE_RE = re.compile(r"```json\b", re.IGNORECASE)

# Одна тема в разных написаниях — для проверки «RAG покрыл нужный обмен».
_API_KEY_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"linkedevents", "getlinkedevents"}),
    frozenset({"getoperationwithdetails", "getoperationswithdetails"}),
)


def evidence_has_contract_body(text: str) -> bool:
    """Есть ли в evidence реальный контракт (JSON / таблица полей)."""
    return chunk_has_contract_body(text or "")


def _expand_api_key_aliases(keys: set[str]) -> set[str]:
    expanded = set(keys)
    for group in _API_KEY_ALIAS_GROUPS:
        if expanded & group:
            expanded |= group
    return expanded


def requested_api_keys(*texts: str) -> set[str]:
    """Нормализованные ключи API из запроса (с алиасами)."""
    keys = {
        _normalize_api_key(api)
        for api in extract_api_ids(" ".join(t for t in texts if t))
    }
    keys.discard("")
    return _expand_api_key_aliases(keys)


def evidence_covers_requested_apis(rag: str, *query_texts: str) -> bool:
    """Контракт в RAG есть и он про запрошенный обмен (не чужой SendOperations).

    Без API в запросе — достаточно любого contract body (как раньше).
    """
    targets = requested_api_keys(*query_texts)
    if not evidence_has_contract_body(rag):
        return False
    if not targets:
        return True
    rag_keys: set[str] = {
        _normalize_api_key(api) for api in extract_api_ids(rag or "")
    }
    # Поля вроде linkedEvents тоже считаем упоминанием темы.
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{5,}", rag or ""):
        key = _normalize_api_key(token)
        if key:
            rag_keys.add(key)
    rag_keys.discard("")
    rag_keys = _expand_api_key_aliases(rag_keys)
    # Достаточно покрытия хотя бы одного целевого API-семейства.
    return bool(targets & rag_keys)

def draft_claims_contract(text: str) -> bool:
    """Черновик претендует на JSON/пример контракта."""
    raw = text or ""
    if _JSON_FENCE_RE.search(raw):
        return True
    if raw.count("{") >= 2 and raw.count('":') >= 4:
        return True
    return False


def brief_wants_contract(*texts: str) -> bool:
    blob = "\n".join(t for t in texts if t)
    if extract_api_ids(blob):
        return True
    low = blob.lower()
    return any(
        token in low
        for token in (
            "пример",
            "json",
            "request",
            "response",
            "запрос",
            "ответ",
            "контракт",
            "параметр",
            "обмен",
        )
    )


def fetch_lexical_contracts(
    kb: SearchKbHandler, query: str, *, topic_query: str = ""
) -> str:
    """Special path + lexical grep: контракты по API-id / формулировке."""
    del topic_query  # совместимость сигнатуры; фильтров темы нет
    q = (query or "").strip()
    if not q:
        return ""
    # Налог в GOWD лежит как TAX_WITHHOLDING (SIHIST-3367), не BASE_ORDER (3503).
    fetch_q = q
    if re.search(r"налог|\btax\b", q, re.I) and extract_api_ids(q):
        fetch_q = f"{q} TAX_WITHHOLDING tax MONEY_DIAS"
    pack = kb.fetch_api_contracts(fetch_q)
    if pack.strip():
        return pack.strip()
    # Нет явных API-id — обычный grep с уклоном в контракт.
    if brief_wants_contract(q):
        hit = kb.grep_kb(f"{fetch_q} пример JSON параметры запроса ответа")
        if hit and "Ничего не найдено" not in hit and "пуста" not in hit:
            return hit.strip()
    return ""


def expand_search_context(
    kb: SearchKbHandler,
    *,
    query: str,
    rag_context: str,
    extra_queries: list[str] | None = None,
    topic_query: str = "",
    only_if_gap: bool = True,
) -> str:
    """Склеить reranked RAG + опциональный lexical при дырке в контракте.

    Если lexical добрал целевой API — он идёт ПЕРВЫМ (иначе answer обрезает
    KB с головы и видит только FE-шум из Qdrant). Без lexical остаётся RAG.
    При ``only_if_gap`` lexical не зовём, если в RAG уже есть контракт
    запрошенного обмена.
    """
    del topic_query  # поиск идёт по query; отдельной «темы» нет
    rag = (rag_context or "").strip()
    queries: list[str] = []
    for item in (query, *(extra_queries or [])):
        q = (item or "").strip()
        if q and q not in queries:
            queries.append(q)

    wants = brief_wants_contract(*queries) if queries else False
    has_rag_contract = evidence_covers_requested_apis(rag, *queries)
    need_lexical = bool(queries) and (
        not only_if_gap or (wants and not has_rag_contract)
    )

    lexical_parts: list[str] = []
    if need_lexical:
        seen_norm: set[str] = set()
        for q in queries:
            pack = fetch_lexical_contracts(kb, q)
            if not pack:
                continue
            norm = re.sub(r"\s+", " ", pack[:800]).lower()
            if norm in seen_norm:
                continue
            seen_norm.add(norm)
            lexical_parts.append(pack)
        if lexical_parts:
            log.info(
                "kb_expand: lexical_parts=%d chars=%d apis=%s gap=%s",
                len(lexical_parts),
                sum(len(p) for p in lexical_parts),
                extract_api_ids(" ".join(queries))[:6],
                not has_rag_contract,
            )
        elif only_if_gap:
            log.info(
                "kb_expand: skip/no-hit gap=%s wants=%s has_target_contract=%s",
                not has_rag_contract,
                wants,
                has_rag_contract,
            )
    elif only_if_gap and has_rag_contract:
        log.info("kb_expand: skip — RAG already has target API contract")

    parts: list[str] = []
    if lexical_parts:
        lexical_blob = "\n\n---\n\n".join(lexical_parts)
        if len(lexical_blob) > _MAX_LEXICAL_GAP_CHARS:
            lexical_blob = lexical_blob[:_MAX_LEXICAL_GAP_CHARS] + (
                f"\n\n...[обрезано lexical gap: {_MAX_LEXICAL_GAP_CHARS}]"
            )
        # Целевой контракт важнее FE-чанков из rerank — иначе обрежется.
        parts.append(
            "## Контракты из файлов KB (lexical / API-id)\n\n" + lexical_blob
        )
    if rag:
        parts.append("## RAG (Qdrant)\n\n" + rag)

    if not parts:
        return ""

    merged = "\n\n".join(parts)
    if len(merged) > _MAX_MERGED_CHARS:
        merged = merged[:_MAX_MERGED_CHARS] + (
            f"\n\n...[обрезано expand: {_MAX_MERGED_CHARS}]"
        )
    return merged


def contract_gap_answer(feature_brief: str) -> str:
    """Честный отказ: в KB нет полного request/response — не выдумывать."""
    apis = extract_api_ids(feature_brief)
    api_hint = f" ({', '.join(apis[:4])})" if apis else ""
    return (
        f"В базе знаний нет полного примера request/response по запрошенному "
        f"обмену{api_hint}. Не выдумываю поля и JSON. "
        "Уточни имя обмена/тикет SIHIST или приложи фрагмент контракта."
    )
