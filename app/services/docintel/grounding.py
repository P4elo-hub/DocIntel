"""Жёсткая (не-LLM) проверка: JSON/контракт в ответе должен опираться на Qdrant.

Используется validate_agent после/вместо мягкого LLM-review, чтобы
самодельные «похожие» JSON не проходили только потому что отдельные
токены встречаются в таблицах.
"""

from __future__ import annotations

import json
import re
from typing import Any

_SOURCES_TAIL_RE = re.compile(r"(?im)^#{1,3}\s*Источники\b[\s\S]*$")
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_GAP_ANSWER = (
    "В базе знаний (Qdrant) нет дословного примера JSON/контракта, "
    "совпадающего по структуре с запросом. Не выдумываю поля и обёртки. "
    "Уточни формулировку или дополни корпус."
)


def gap_refusal_text() -> str:
    return _GAP_ANSWER


def strip_sources_section(text: str) -> str:
    return _SOURCES_TAIL_RE.sub("", text or "").strip()


_TABLE_BLOCK_RE = re.compile(r"(?:^\|[^\n]+\|\s*\n){3,}", re.MULTILINE)


def evidence_excerpt_answer(
    evidence: str,
    *,
    limit: int = 7_000,
    prefer_tokens: tuple[str, ...] | None = None,
) -> str:
    """Механический ответ из Qdrant, когда LLM врёт «Отказ» при живом evidence.

    Не генерирует новый JSON — только выдержки (JSON/таблицы/фрагмент) из RAG.
    """
    ev = evidence or ""
    parts: list[str] = [
        "В Qdrant найдены релевантные фрагменты. Ниже — дословные выдержки "
        "из базы знаний (без домыслов модели)."
    ]

    boost = prefer_tokens or (
        "varmargin",
        "screendata",
        "linkedevents",
        "operationtype",
        "operation_type",
        "operations",
        "history",
    )
    scored: list[tuple[float, Any]] = []
    for obj in extract_json_objects(ev):
        raw = json.dumps(obj, ensure_ascii=False)
        low = raw.lower()
        score = 0.0
        for token in boost:
            if token.lower() in low:
                score += 3.0
        score += min(len(key_paths(obj)), 25) * 0.05
        scored.append((score, obj))
    scored.sort(key=lambda item: -item[0])
    for i, (_, obj) in enumerate(scored[:3], 1):
        blob = json.dumps(obj, ensure_ascii=False, indent=2)
        if len(blob) > 3_500:
            blob = blob[:3_500] + "\n…"
        parts.append(f"### JSON из KB ({i})\n```json\n{blob}\n```")

    tables = _TABLE_BLOCK_RE.findall(ev)
    interesting = [
        t
        for t in tables
        if re.search(
            r"(?i)varmargin|вариацион|screendata|operationtype|тип|наименован",
            t,
        )
    ]
    for i, table in enumerate((interesting or tables)[:3], 1):
        parts.append(f"### Таблица из KB ({i})\n{table.strip()[:2_500]}")

    if len(parts) == 1:
        m = re.search(
            r"(?is).{0,120}(varmargin|вариацион\w*).{0,900}",
            ev,
        )
        if m:
            parts.append(f"### Фрагмент из KB\n{m.group(0).strip()}")
        else:
            parts.append(f"### Фрагмент из KB\n{ev[:2_500].strip()}")

    return "\n\n".join(parts)[:limit].rstrip()


def _parse_json_candidate(raw: str) -> Any | None:
    raw = (raw or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Обрезанный пример из чанка — пробуем найти сбалансированный префикс.
        depth = 0
        for i, ch in enumerate(raw):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[: i + 1])
                    except json.JSONDecodeError:
                        return None
        return None


def extract_json_objects(text: str) -> list[Any]:
    """Достаёт JSON-объекты из fenced-блоков и «голых» `{...}`."""
    text = text or ""
    found: list[Any] = []
    seen: set[str] = set()

    def _add(obj: Any) -> None:
        try:
            key = json.dumps(obj, sort_keys=True, ensure_ascii=False)[:500]
        except (TypeError, ValueError):
            return
        if key in seen:
            return
        seen.add(key)
        found.append(obj)

    for m in _FENCED_JSON_RE.finditer(text):
        obj = _parse_json_candidate(m.group(1))
        if isinstance(obj, dict):
            _add(obj)

    # Голые объекты: сканируем по `{`.
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        # Не дублируем то, что уже взяли из fence.
        window = text[start : start + 12_000]
        obj = _parse_json_candidate(window)
        if isinstance(obj, dict) and len(obj) >= 1:
            _add(obj)
        if len(found) >= 12:
            break
    return found


def key_paths(obj: Any, prefix: str = "") -> set[str]:
    """Набор путей ключей: screenData.type, content.totalSum, operations[].type."""
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.add(path.lower())
            paths |= key_paths(value, path)
    elif isinstance(obj, list) and obj:
        next_prefix = f"{prefix}[]" if prefix else "[]"
        # Берём первый элемент-объект как форму массива.
        for item in obj[:3]:
            if isinstance(item, (dict, list)):
                paths |= key_paths(item, next_prefix)
                break
    return paths


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _path_coverage(draft_paths: set[str], evidence_paths: set[str]) -> float:
    """Доля путей черновика, для которых есть тот же путь или тот же leaf в evidence."""
    if not draft_paths:
        return 1.0
    ev_leaves = {p.split(".")[-1].replace("[]", "") for p in evidence_paths}
    hit = 0
    for path in draft_paths:
        leaf = path.split(".")[-1].replace("[]", "")
        if path in evidence_paths:
            hit += 1
        elif leaf in ev_leaves and "." in path:
            # leaf-only для вложенных путей считаем слабым совпадением
            hit += 0.35
    return hit / len(draft_paths)


def _minify(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def check_contract_alignment(draft: str, brief: str) -> tuple[bool, str]:
    """Черновик должен быть тем же обменом/слоем, что в запросе (+история в brief).

    Иначе validate «чинит» Linked Events → чужой screenData комиссии из RAG
    и hard-ground пропускает, потому что JSON формально есть в Qdrant.
    """
    b = (brief or "").lower()
    body = strip_sources_section(draft)
    draft_objs = [o for o in extract_json_objects(body) if len(key_paths(o)) >= 4]
    if not draft_objs:
        return True, "no_substantial_json"

    blob = _minify(json.dumps(draft_objs[0], ensure_ascii=False)).lower()
    has_linked = "linkedevents" in blob
    has_screen = "screendata" in blob

    wants_linked = bool(
        re.search(r"get[_\s-]*linked|linked\s*events|linkedin|linkedevents", b)
    )
    wants_composite = bool(
        re.search(
            r"screendata|композит|operationdetails|operationshistory|"
            r"деталка|лент[аеуы]|на\s+фронт",
            b,
        )
    )

    if wants_linked and not wants_composite and not has_linked:
        return False, "wanted_linked_events_missing_linkedEvents"
    if wants_linked and not wants_composite and has_screen and not has_linked:
        return False, "wanted_linked_events_got_screendata"
    if wants_composite and not wants_linked and has_linked and not has_screen:
        return False, "wanted_composite_got_linked_events"
    return True, "ok"


def check_json_grounded(
    draft: str,
    evidence: str,
    *,
    brief: str = "",
) -> tuple[bool, str]:
    """True — JSON в draft достаточно совпадает с JSON/структурой из Qdrant evidence."""
    align_ok, align_reason = check_contract_alignment(draft, brief)
    if not align_ok:
        return False, align_reason

    body = strip_sources_section(draft)
    draft_objs = [o for o in extract_json_objects(body) if len(key_paths(o)) >= 4]
    if not draft_objs:
        return True, "no_substantial_json"

    evidence_objs = extract_json_objects(evidence)
    evidence_path_sets = [key_paths(o) for o in evidence_objs if len(key_paths(o)) >= 3]

    # Дословный кусок (minify): если большой фрагмент draft JSON есть в evidence — ок.
    ev_min = _minify(evidence)
    for obj in draft_objs:
        raw = json.dumps(obj, ensure_ascii=False)
        piece = _minify(raw)
        if len(piece) >= 80 and piece[: min(180, len(piece))] in ev_min:
            return True, "literal_json_substring"

    draft_path_sets = [key_paths(o) for o in draft_objs]
    if not evidence_path_sets:
        # В RAG нет ни одного JSON-примера, а в ответе большой JSON — выдумка.
        biggest = max(len(p) for p in draft_path_sets)
        if biggest >= 5:
            return False, f"draft_json_without_rag_json_example paths={biggest}"
        return True, "no_rag_json_trivial_draft"

    best_j = 0.0
    best_c = 0.0
    for dpaths in draft_path_sets:
        for epaths in evidence_path_sets:
            best_j = max(best_j, _jaccard(dpaths, epaths))
            best_c = max(best_c, _path_coverage(dpaths, epaths))

    # Жёсткие пороги: «похожие» обёртки (screenData+operations vs history.feed) режутся.
    if best_j < 0.34 and best_c < 0.45:
        return False, f"json_structure_mismatch jaccard={best_j:.2f} coverage={best_c:.2f}"
    return True, f"ok jaccard={best_j:.2f} coverage={best_c:.2f}"
