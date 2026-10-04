"""Handler: поиск по проектной документации.

Общее правило для любого обмена/фичи: если в запросе есть идентификатор
API (CamelCase / SCREAMING_SNAKE) — поднимаем файлы по имени и секции
«запрос/ответ» выше, чем посторонний token-overlap (логирование и т.п.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_API_ID_RE = re.compile(
    r"\b(?:Get|Set|Send|Create|Update|Delete|List|Fetch|Post|Put|Patch)"
    r"[A-Z][A-Za-z0-9]+"
    # SCREAMING_SNAKE и Whisper-вариант с дефисами: GET-LINKED-EVENTS
    r"|(?:[A-Z][A-Z0-9]+(?:[_-][A-Z0-9]+)+)\b"
    # «SEND OPERATIONS» / «GET LINKED EVENTS» — пробелы вместо _
    r"|(?:(?:GET|SET|SEND|CREATE|UPDATE|DELETE|LIST|FETCH|POST|PUT|PATCH)"
    r"(?:\s+[A-Z][A-Z0-9]*){1,5})\b"
    # ScreenApi, HistoryOps, Composite (сервисы/обмены без Get/Set-префикса)
    r"|(?:[A-Z][a-zA-Z0-9]+(?:Api|API|Ops))\b"
    r"|\bComposite\b"
)
_CONTRACT_HEADING_HINTS = (
    "запрос/ответ",
    "запроса/ответа",
    "описание запроса",
    "параметры запроса",
    "параметры ответа",
    "пример запроса",
    "пример ответа",
    "request",
    "response",
    "тело запроса",
    "тело ответа",
)
_NOISE_HEADING_HINTS = (
    "логирован",
    "мониторинг",
    "logging",
    "метрик",
    "prometheus",
    "elasticsearch",
    "содержание",
    "оглавление",
)

# Титульные/мета-чанки: имя API в заголовке файла, но без тела контракта.
_META_BODY_HINTS = (
    "jira.sberbank",
    "|трайб|",
    "|сквод",
    "done|",
    "viewavatar",
)

# Лимиты ответа search_kb — write-агенту нужен контракт целиком (поля ответа
# часто лежат на 3–10k символов ниже заголовка секции).
_MAX_CHUNK_CHARS = 14_000
_MAX_TOTAL_CHARS = 28_000
_TOP_K = 6


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zа-яё0-9]+", text.lower()) if len(token) > 2}


def _normalize_api_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def extract_api_ids(text: str) -> list[str]:
    """Имена обменов/методов из любого брифа: CamelCase и SCREAMING_SNAKE + алиасы."""
    found = list(dict.fromkeys(_API_ID_RE.findall(text or "")))
    extras: list[str] = []
    for name in found:
        # Whisper/ASR: GET-LINKED-EVENTS → GET_LINKED_EVENTS
        if "-" in name:
            name = name.replace("-", "_")
            extras.append(name)
        # Часто путают singular/plural: GetOperationWithDetails → GetOperations…
        if re.fullmatch(r"GetOperationWithDetails", name) or re.fullmatch(
            r"GET_OPERATION_WITH_DETAILS", name.replace("-", "_")
        ):
            extras.append("GetOperationsWithDetails")
            extras.append("GET_OPERATIONS_WITH_DETAILS")
        # «SEND OPERATIONS» → SEND_OPERATIONS (+ CamelCase)
        if " " in name:
            snake = re.sub(r"\s+", "_", name.strip()).upper()
            extras.append(snake)
            parts = snake.lower().split("_")
            extras.append(
                parts[0].capitalize() + "".join(p.capitalize() for p in parts[1:])
            )
            continue
        if "_" not in name and re.match(
            r"^(Get|Set|Send|Create|Update|Delete|List|Fetch|Post|Put|Patch)",
            name,
        ):
            extras.append(re.sub(r"(?<!^)([A-Z])", r"_\1", name).upper())
        if "_" in name:
            parts = name.lower().split("_")
            if parts[0] in {
                "get", "set", "send", "create", "update", "delete",
                "list", "fetch", "post", "put", "patch",
            }:
                extras.append(
                    parts[0].capitalize() + "".join(p.capitalize() for p in parts[1:])
                )
    return list(dict.fromkeys([*found, *extras]))


@dataclass(frozen=True)
class DocChunk:
    source: str
    heading: str
    text: str

    @property
    def label(self) -> str:
        if self.heading:
            return f"[{self.source} » {self.heading}]"
        return f"[{self.source}]"


def _strip_front_matter(content: str) -> str:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return content


def _parse_markdown_chunks(
    path: Path, content: str, *, source: str | None = None
) -> list[DocChunk]:
    content = _strip_front_matter(content)
    relative = source or path.name

    heading_stack: list[tuple[int, str]] = []
    current_body: list[str] = []
    chunks: list[DocChunk] = []

    def flush() -> None:
        if not heading_stack and not current_body:
            return
        heading = " » ".join(title for _, title in heading_stack)
        body = "\n".join(current_body).strip()
        text = f"{heading}\n{body}".strip() if heading else body
        if text:
            chunks.append(DocChunk(source=relative, heading=heading, text=text))

    for line in content.splitlines():
        match = _HEADER_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = [(lvl, name) for lvl, name in heading_stack if lvl < level]
            heading_stack.append((level, title))
            current_body = []
            continue
        current_body.append(line)

    flush()

    if not chunks and content.strip():
        chunks.append(DocChunk(source=relative, heading="", text=content.strip()))

    return chunks


def _load_txt_chunks(path: Path) -> list[DocChunk]:
    if not path.is_file():
        return []
    return [
        DocChunk(source=path.name, heading="", text=line.strip().lstrip("- ").strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_docs_chunks(docs_dir: Path) -> list[DocChunk]:
    if not docs_dir.is_dir():
        return []

    chunks: list[DocChunk] = []
    for path in sorted(docs_dir.rglob("*.md")):
        try:
            rel = path.relative_to(docs_dir).as_posix()
        except ValueError:
            rel = path.name
        chunks.extend(
            _parse_markdown_chunks(
                path,
                path.read_text(encoding="utf-8"),
                source=rel,
            )
        )
    return chunks


def _text_mentions_api(text: str, api_ids: list[str]) -> bool:
    """API упомянут в теле чанка (файл может называться иначе, напр. «Композит»)."""
    if not text or not api_ids:
        return False
    low = text.lower()
    compact = re.sub(r"[^a-z0-9]", "", low)
    for api in api_ids:
        if api.lower() in low:
            return True
        key = _normalize_api_key(api)
        if key and key in compact:
            return True
    return False


def _source_matches_api(source: str, api_ids: list[str]) -> bool:
    source_key = _normalize_api_key(source)
    for api in api_ids:
        if _normalize_api_key(api) and _normalize_api_key(api) in source_key:
            return True
    return False


def _heading_is_contract(heading: str) -> bool:
    h = heading.lower()
    return any(hint in h for hint in _CONTRACT_HEADING_HINTS)


def _heading_is_noise(heading: str) -> bool:
    h = heading.lower()
    return any(hint in h for hint in _NOISE_HEADING_HINTS)


def chunk_has_contract_body(text: str) -> bool:
    """Есть ли в тексте реальный контракт (JSON/таблица полей), а не титул/сценарий."""
    raw = text or ""
    low = raw.lower()
    if "```json" in low:
        return True
    if any(
        marker in low
        for marker in (
            "| параметр",
            "| имя поля",
            "| поле |",
            "параметры запроса",
            "параметры ответа",
            "пример запроса",
            "пример ответа",
            "тело запроса",
            "тело ответа",
        )
    ):
        return True
    # Таблица типов OpenAPI-стиля
    if re.search(
        r"\|\s*(string|int|integer|boolean|object|array|number|enum)\s*\|",
        low,
    ):
        return True
    # JSON-объект в тексте (не URL/confluence-мусор)
    if (
        low.count("{") >= 2
        and low.count("}") >= 2
        and low.count('":') >= 8
        and low.count("http") < 5
    ):
        return True
    return False


# Обратная совместимость для внутренних вызовов / тестов.
_chunk_has_contract_body = chunk_has_contract_body


def _contract_field_richness(text: str) -> int:
    """Насыщенность контракта без привязки к полям конкретного API."""
    low = (text or "").lower()
    score = 0
    if "```json" in low:
        score += 3
    # Плотность JSON-ключей / markdown-таблиц — универсальные сигналы контракта.
    score += min(low.count('":'), 20)
    score += min(low.count("|"), 30) // 3
    if "параметр" in low or "пример" in low:
        score += 1
    return score


def _chunk_is_meta_noise(text: str, heading: str) -> bool:
    low = (text or "").lower()
    h = (heading or "").lower()
    if "содержание" in h or "оглавление" in h:
        return True
    meta_hits = sum(1 for hint in _META_BODY_HINTS if hint in low)
    if meta_hits >= 2 and not _chunk_has_contract_body(text):
        return True
    return False


def _clip(text: str, limit: int = _MAX_CHUNK_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n...[обрезано: {len(text)} символов всего]"


def _query_wants_frontend_composite(query: str) -> bool:
    """Запрос про фронт/композит/деталку/ленту — нужен FE-слой, не BE get_all."""
    low = (query or "").lower()
    return bool(
        re.search(
            r"фронт|детал|композит|screenapi|screen\s*api|"
            r"operationdetails|screendata|\bлент|\bfe\b",
            low,
        )
    )


def _query_wants_detail_card(query: str) -> bool:
    """Карточка деталки (operationDetails), не лента."""
    low = (query or "").lower()
    if re.search(r"operationdetails|карточк", low):
        return True
    if re.search(r"деталк|детальн\w*\s+информац", low):
        return True
    # «детализацией» из condense — тоже про деталку, если явно не лента.
    if re.search(r"детал", low) and not re.search(r"\bлент", low):
        return True
    return False


def _query_wants_feed_screen(query: str) -> bool:
    """Экран ленты (operationsHistory).

    Голое «Ленты» в имени папки «Композит, Экран, Ленты, ФЕ» — не сигнал ленты,
    если в запросе уже есть деталка.
    """
    low = (query or "").lower()
    if re.search(
        r"operationshistory|на\s+ленте|в\s+ленте|экран.?лент|ответ\s+в\s+лент",
        low,
    ):
        return True
    if re.search(r"\bлент", low) and not re.search(r"детал", low):
        return True
    return False


def _query_wants_tax(query: str) -> bool:
    return bool(re.search(r"налог|\btax\b", (query or "").lower()))


def _query_wants_cancel(query: str) -> bool:
    return bool(re.search(r"отмен|cancel", (query or "").lower()))


def _source_is_frontend_composite(source: str) -> bool:
    s = (source or "").lower().replace("\\", "/")
    if "sihist_markdown_front" in s and (
        "фронт композит" in s
        or "композит_" in s
        or "композит-" in s
        or "/композит" in s
    ):
        return True
    if "_(fe).md" in s and "композит" in s:
        return True
    return False


def _source_is_detail_fe(source: str) -> bool:
    s = (source or "").lower().replace("\\", "/")
    return "деталк" in s and _source_is_frontend_composite(source)


def _source_is_feed_fe(source: str) -> bool:
    s = (source or "").lower().replace("\\", "/")
    return bool(re.search(r"лент|экран_лент", s)) and _source_is_frontend_composite(
        source
    )


def _source_is_cancel_fe(source: str) -> bool:
    s = (source or "").lower().replace("\\", "/")
    return bool(re.search(r"отмен|cancel", s)) and "sihist_markdown_front" in s


def _heading_is_nfr_support(heading: str) -> bool:
    h = (heading or "").lower()
    return bool(
        re.search(
            r"нефункциональн|сопровожден|мониторинг|логирован|безопасн|"
            r"требовани[яй]\s+к\s+настрой",
            h,
        )
    )


def _source_is_be_operations_blob(source: str, text: str) -> bool:
    """Толстые BE-простыни get_all / общие таблицы операций."""
    s = (source or "").lower().replace("\\", "/")
    t = (text or "").lower()
    if "sihist_markdown_front" in s or "фронт композит" in s:
        return False
    if "get_all" in s or "operation/v2/get_all" in t or "operations/get_all" in t:
        return True
    if (
        "sihist_markdown_back" in s
        and len(text) > 12_000
        and "transaction_buy" in t
        and ("параметры ответа" in t or "```json" in t)
    ):
        return True
    return False


def _query_anchor_terms(query: str) -> list[str]:
    """Термины для якорения окна обрезки (приоритетнее первого ```json)."""
    terms: list[str] = []
    low = (query or "").lower()
    for token in _tokenize(query):
        if len(token) >= 4:
            terms.append(token)
        # налогам/налога → налог; деталка → деталк
        if len(token) >= 5:
            terms.append(token[:5])
        if len(token) >= 6:
            terms.append(token[:6])
    if re.search(r"налог|\btax\b", low):
        terms.extend(
            [
                "налог",
                "налоги",
                "tax",
                "tax_withholding",
                "TAX_WITHHOLDING",
                'operationtype": "tax',
                "operation_type",
                "списание налога",
                "удержание налога",
                "удержание суммы налога",
            ]
        )
    if re.search(r"вармарж|вариацион|varmargin", low):
        terms.extend(["varmargin", "вариацион", "вармарж"])
    if _query_wants_detail_card(query):
        terms.extend(
            [
                "деталк",
                "operationdetails",
                "operation details",
                '"type": "operationdetails"',
                'type": "operationdetails',
            ]
        )
    if _query_wants_feed_screen(query):
        terms.extend(
            [
                "operationshistory",
                '"type": "operationshistory"',
                'type": "operationshistory',
            ]
        )
    if re.search(r"композит|screenapi|фронт", low):
        terms.extend(["композит", "screenapi", "screendata"])

    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower().strip()
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _find_all_positions(haystack: str, needle: str, *, limit: int = 40) -> list[int]:
    if not haystack or not needle:
        return []
    positions: list[int] = []
    start = 0
    while len(positions) < limit:
        idx = haystack.find(needle, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + max(1, len(needle))
    return positions


def _clip_contract_window(
    text: str,
    *,
    api_ids: list[str] | None = None,
    query: str = "",
    limit: int = _MAX_CHUNK_CHARS,
) -> str:
    """Для больших секций вырезает окно вокруг темы запроса, не первого JSON файла."""
    if not text:
        return text

    low = text.lower()
    scored_anchors: list[tuple[int, int]] = []  # (score, pos)

    for term in _query_anchor_terms(query):
        weight = 30 if len(term) >= 5 else 15
        if term in {"налог", "налоги", "tax", "varmargin", "деталк", "композит"}:
            weight = 50
        if "operationtype" in term or "operation_type" in term:
            weight = 60
        for pos in _find_all_positions(low, term):
            look = low[pos : pos + min(6_000, limit)]
            bonus = 0
            if "```json" in look or '"operationtype"' in look or "operationtype" in look:
                bonus += 25
            if "пример" in look:
                bonus += 8
            scored_anchors.append((weight + bonus, pos))

    for api in api_ids or []:
        key = _normalize_api_key(api)
        if not key:
            continue
        compact = re.sub(r"[^a-z0-9]", "", low)
        idx = compact.find(key)
        if idx >= 0:
            scored_anchors.append((40, min(len(text) - 1, idx)))

    # Fallback: общие маркеры контракта — только если тема запроса не нашлась.
    if not scored_anchors:
        for marker in (
            "```json",
            "параметры ответа",
            "параметры запроса",
            "пример ответа",
            "пример запроса",
            "описание ответа",
            "описание запроса",
            "тело ответа",
            "тело запроса",
        ):
            pos = low.find(marker)
            if pos >= 0:
                scored_anchors.append((5, pos))

    if not scored_anchors:
        return _clip(text, limit)

    scored_anchors.sort(key=lambda item: (-item[0], item[1]))
    best_score, anchor = scored_anchors[0]
    # Тема запроса (налог/tax/…) — не тянуть длинный lookback с чужим JSON выше.
    if best_score >= 40:
        block = text.rfind("\n\n", max(0, anchor - 500), anchor)
        start = block + 2 if block >= 0 else max(0, anchor - 80)
        # Если упёрлись в чужой/свой fence выше якоря — начать после закрытия fence.
        prev_fence = text.rfind("```", max(0, start - 20), anchor)
        if prev_fence >= start:
            # Якорь внутри JSON-примера темы — взять с начала этого fence.
            start = prev_fence
        else:
            prev_close = text.rfind("```", 0, start)
            if prev_close >= 0:
                # После закрывающего fence предыдущего примера.
                after = text.find("\n", prev_close + 3)
                if after > 0 and after < anchor:
                    start = after + 1
    else:
        start = max(0, anchor - 500)
    end = min(len(text), start + limit)
    # Не откатывать start назад «чтобы заполнить limit»: у конца файла это
    # снова затягивает transaction_buy / чужие примеры выше по тексту.
    if best_score < 40 and end - start < limit:
        start = max(0, end - limit)
    piece = text[start:end]
    prefix = "...[начало секции обрезано]\n\n" if start > 0 else ""
    suffix = f"\n\n...[обрезано: {len(text)} символов всего]" if end < len(text) else ""
    return prefix + piece + suffix


def _heading_is_usecase(heading: str) -> bool:
    h = (heading or "").lower()
    return any(
        marker in h
        for marker in (
            "процесс/сервис",
            "as is",
            "to be",
            "шаги процесса",
            "use case",
            "сценарий",
        )
    )


def _contract_rank(chunk: DocChunk) -> tuple[int, int, int, int, int]:
    """Меньше = лучше для forced-списка контрактов."""
    body = 0 if _chunk_has_contract_body(chunk.text) else 1
    heading = 0 if _heading_is_contract(chunk.heading) else 1
    noise = 1 if _chunk_is_meta_noise(chunk.text, chunk.heading) else 0
    # Use case AS IS/TO BE часто тащит API по имени, но это не схема ответа.
    usecase = 1 if _heading_is_usecase(chunk.heading) else 0
    # Больше известных полей контракта — выше (invert).
    richness = -_contract_field_richness(chunk.text)
    return (noise, usecase, body, richness, heading)


def _query_wants_contract(query: str, api_ids: list[str]) -> bool:
    return bool(api_ids) or any(
        token in (query or "").lower()
        for token in (
            "параметр",
            "поле",
            "запрос",
            "ответ",
            "request",
            "response",
            "yield",
            "доходност",
            "документац",
            "контракт",
            "пример",
            "json",
        )
    )


class SearchKbHandler:
    def __init__(
        self,
        knowledge_base_path: Path | None = None,
        docs_dir: Path | None = None,
    ) -> None:
        self._chunks: list[DocChunk] = []
        self._docs_dir = docs_dir

        if docs_dir is not None:
            self._chunks.extend(_load_docs_chunks(docs_dir))

        if knowledge_base_path is not None:
            self._chunks.extend(_load_txt_chunks(knowledge_base_path))

    def grep_kb(self, query: str) -> str:
        """Read-only lexical поиск по KB (алиас search_kb для tool-surface)."""
        return self.search_kb(query)

    def read_kb_section(
        self,
        source_hint: str,
        heading_hint: str = "",
        *,
        api_ids: list[str] | None = None,
    ) -> str:
        """Открыть секцию файла KB целиком (по имени файла / заголовку)."""
        source_hint = (source_hint or "").strip()
        heading_hint = (heading_hint or "").strip()
        if not source_hint and not heading_hint:
            return "Ничего не найдено: укажите source_hint или heading_hint."
        if not self._chunks:
            return "База документации пуста."

        source_key = _normalize_api_key(source_hint)
        heading_key = heading_hint.lower()
        matched: list[DocChunk] = []
        for chunk in self._chunks:
            source_ok = (
                not source_hint
                or source_key in _normalize_api_key(chunk.source)
                or source_hint.lower() in chunk.source.lower()
            )
            heading_ok = (
                not heading_hint
                or heading_key in (chunk.heading or "").lower()
            )
            if source_ok and heading_ok:
                matched.append(chunk)

        if not matched:
            return (
                f"Секция не найдена: source={source_hint!r} "
                f"heading={heading_hint!r}"
            )

        matched.sort(key=_contract_rank)
        ids = api_ids or extract_api_ids(f"{source_hint} {heading_hint}")
        return self._format_chunks(
            matched[:3],
            query=f"{source_hint} {heading_hint}".strip(),
            api_ids=ids,
            wants_contract=True,
            header_prefix="Секция KB",
        )

    def fetch_api_contracts(self, query: str, *, top_k: int = 4) -> str:
        """Special path: для API-id вытащить request/response секции целиком."""
        query = (query or "").strip()
        api_ids = extract_api_ids(query)
        if not api_ids:
            return ""
        if not self._chunks:
            return ""

        forced = self._contract_candidates(api_ids)
        if not forced:
            # Фоллбек: широкий lexical search с приоритетом контрактов.
            hit = self.search_kb(
                f"{query} параметры запроса ответа пример JSON request response"
            )
            if hit and "Ничего не найдено" not in hit:
                return hit
            return ""

        # Не брать «самый жирный» файл (часто TRADE/BASE_ORDER), а релевантный
        # теме запроса (налог → TAX_WITHHOLDING в SIHIST-3367).
        q_tokens = _tokenize(query)
        forced.sort(
            key=lambda chunk: -self._score_chunk(
                chunk, q_tokens, api_ids, True, query=query
            )
        )

        return self._format_chunks(
            forced[:top_k],
            query=query,
            api_ids=api_ids,
            wants_contract=True,
            header_prefix=(
                f"Контракты API ({', '.join(api_ids[:4])})"
            ),
        )

    def search_kb(self, query: str) -> str:
        query = query.strip()
        if not query:
            return "Ничего не найдено: пустой запрос."

        if not self._chunks:
            return (
                "База документации пуста. Добавьте .md файлы в app/data/docs/ "
                "или записи в knowledge_base.txt."
            )

        query_tokens = _tokenize(query)
        if not query_tokens and not extract_api_ids(query):
            return "Ничего не найдено: укажите ключевые слова."

        api_ids = extract_api_ids(query)
        wants_contract = _query_wants_contract(query, api_ids)

        scored: list[tuple[int, DocChunk]] = []
        for chunk in self._chunks:
            score = self._score_chunk(
                chunk, query_tokens, api_ids, wants_contract, query=query
            )
            if score > 0:
                scored.append((score, chunk))

        if not scored and not api_ids:
            return f"Ничего не найдено по запросу: {query}"

        scored.sort(key=lambda item: item[0], reverse=True)

        # Контрактные секции из файлов с именем обмена — всегда в начале.
        forced = self._contract_candidates(api_ids) if api_ids else []
        seen: set[str] = {f"{c.source}::{c.heading}" for c in forced}

        selected: list[DocChunk] = []
        for chunk in forced:
            selected.append(chunk)
            if len(selected) >= _TOP_K:
                break
        for _, chunk in scored:
            key = f"{chunk.source}::{chunk.heading}"
            if key in seen:
                continue
            if wants_contract and _chunk_is_meta_noise(chunk.text, chunk.heading):
                continue
            if _chunk_off_topic_for_fe_query(chunk, query):
                continue
            selected.append(chunk)
            seen.add(key)
            if len(selected) >= _TOP_K:
                break

        if not selected:
            return f"Ничего не найдено по запросу: {query}"

        header = f"Найдено {len(selected[:_TOP_K])} фрагментов по запросу «{query}»"
        if api_ids:
            header += f" (API: {', '.join(api_ids[:4])})"
        if forced:
            header += f"; контрактных секций: {len(forced)}"
        return self._format_chunks(
            selected[:_TOP_K],
            query=query,
            api_ids=api_ids,
            wants_contract=wants_contract,
            header_prefix=header,
            include_count_suffix=False,
        )

    def _contract_candidates(self, api_ids: list[str]) -> list[DocChunk]:
        """Контрактные чанки по API-id (JSON/таблицы/запрос-ответ), не титулы."""
        if not api_ids:
            return []
        candidates: list[DocChunk] = []
        seen: set[str] = set()
        for chunk in self._chunks:
            if _chunk_is_meta_noise(chunk.text, chunk.heading):
                continue
            source_ok = _source_matches_api(chunk.source, api_ids)
            text_ok = _text_mentions_api(chunk.text, api_ids)
            if not (source_ok or text_ok):
                continue
            heading_has_api = any(
                _normalize_api_key(api) in _normalize_api_key(chunk.heading)
                for api in api_ids
            )
            if (
                _chunk_has_contract_body(chunk.text)
                or _heading_is_contract(chunk.heading)
                or (source_ok and heading_has_api and len(chunk.text) > 800)
            ):
                key = f"{chunk.source}::{chunk.heading}"
                if key not in seen:
                    candidates.append(chunk)
                    seen.add(key)
        candidates.sort(key=_contract_rank)
        return candidates

    def _format_chunks(
        self,
        chunks: list[DocChunk],
        *,
        query: str,
        api_ids: list[str],
        wants_contract: bool,
        header_prefix: str,
        include_count_suffix: bool = True,
    ) -> str:
        parts: list[str] = []
        total = 0
        for index, chunk in enumerate(chunks, start=1):
            if wants_contract:
                piece = _clip_contract_window(
                    chunk.text, api_ids=api_ids, query=query
                )
            else:
                piece = _clip(chunk.text)
            block = f"{index}. {chunk.label}\n{piece}"
            if total + len(block) > _MAX_TOTAL_CHARS and parts:
                break
            parts.append(block)
            total += len(block)
        if not parts:
            return ""
        header = header_prefix
        if include_count_suffix:
            header = f"{header_prefix}: найдено {len(parts)}"
        return header + ":\n\n" + "\n\n".join(parts)

    @staticmethod
    def _score_chunk(
        chunk: DocChunk,
        query_tokens: set[str],
        api_ids: list[str],
        wants_contract: bool,
        *,
        query: str = "",
    ) -> int:
        text_tokens = _tokenize(chunk.text)
        source_tokens = _tokenize(chunk.source)
        heading_tokens = _tokenize(chunk.heading)

        score = len(query_tokens & text_tokens)
        score += 10 * len(query_tokens & source_tokens)
        score += 5 * len(query_tokens & heading_tokens)

        if api_ids and _source_matches_api(chunk.source, api_ids):
            score += 80
        if api_ids and _text_mentions_api(chunk.text, api_ids):
            score += 50
        for api in api_ids:
            if _normalize_api_key(api) in _normalize_api_key(chunk.heading):
                score += 40

        if wants_contract and _heading_is_contract(chunk.heading):
            score += 50
            if api_ids and (
                _source_matches_api(chunk.source, api_ids)
                or _text_mentions_api(chunk.text, api_ids)
            ):
                score += 40

        if wants_contract and _chunk_has_contract_body(chunk.text):
            score += 120
            if api_ids and (
                _source_matches_api(chunk.source, api_ids)
                or _text_mentions_api(chunk.text, api_ids)
            ):
                score += 80

        if wants_contract and _heading_is_noise(chunk.heading):
            score -= 80

        if wants_contract and _chunk_is_meta_noise(chunk.text, chunk.heading):
            score -= 100

        if wants_contract and _heading_is_usecase(chunk.heading):
            score -= 60

        # Тема «налог» → TAX_WITHHOLDING / tax; чужие TRADE/BASE_ORDER — вниз.
        q_low = (query or "").lower()
        text_l = (chunk.text or "").lower()
        head_l = (chunk.heading or "").lower()
        src_l = (chunk.source or "").lower()
        if re.search(r"налог|\btax\b", q_low):
            if "tax_withholding" in text_l or "tax_withholding" in head_l:
                score += 220
            if re.search(r"\btax\b|налог", text_l) or re.search(
                r"\btax\b|налог", head_l
            ):
                score += 80
            if "3367" in src_l:
                score += 60
            if re.search(r"base_order|trade_order|deal_dias", text_l) and not re.search(
                r"tax_withholding|\btax\b|налог", text_l[:4000]
            ):
                score -= 120
            if "3503" in src_l and "легаси_торгов" in src_l:
                score -= 80

        # Огромные «простыни» без API в имени — слабее.
        if len(chunk.text) > 20_000 and not (
            api_ids and _source_matches_api(chunk.source, api_ids)
        ):
            score -= 10

        # Фронт/деталка/композит → FE-файлы Композита; BE get_all — штраф.
        if _query_wants_frontend_composite(query):
            src_l = (chunk.source or "").lower().replace("\\", "/")
            head_l = (chunk.heading or "").lower()
            text_l = (chunk.text or "").lower()

            if _source_is_frontend_composite(chunk.source):
                score += 160
            if _source_is_be_operations_blob(chunk.source, chunk.text):
                score -= 140
            elif "sihist_markdown_back" in src_l:
                score -= 40

            # NFR / сопровождение почти никогда не то, что нужно для «примера JSON».
            if _heading_is_nfr_support(chunk.heading):
                score -= 250
            elif "функциональные требования" in head_l and (
                "описание выполняемых" in head_l or "пример" in head_l
            ):
                score += 50

            wants_detail = _query_wants_detail_card(query)
            wants_feed = _query_wants_feed_screen(query)
            if wants_detail and not wants_feed:
                if _source_is_detail_fe(chunk.source) and not _source_is_cancel_fe(
                    chunk.source
                ):
                    score += 120
                if _source_is_feed_fe(chunk.source):
                    score -= 180
                if _source_is_cancel_fe(chunk.source) and not _query_wants_cancel(query):
                    score -= 220
                if "operationdetails" in text_l:
                    score += 40
                if "operationshistory" in text_l and "operationdetails" not in text_l:
                    score -= 30
            elif wants_feed and not wants_detail:
                if _source_is_feed_fe(chunk.source):
                    score += 120
                if _source_is_detail_fe(chunk.source):
                    score -= 180
                if "operationshistory" in text_l:
                    score += 40
            elif wants_detail and wants_feed:
                if _source_is_detail_fe(chunk.source):
                    score += 60
                if _source_is_feed_fe(chunk.source):
                    score += 60

            if _query_wants_tax(query):
                if re.search(r"\btax\b|налог", text_l):
                    score += 90
                if _source_is_cancel_fe(chunk.source) and not _query_wants_cancel(query):
                    score -= 180
                if "transaction_buy" in text_l and not re.search(
                    r"\btax\b|налог", text_l[:8_000]
                ):
                    score -= 40

        return score


def _chunk_off_topic_for_fe_query(chunk: DocChunk, query: str) -> bool:
    """Жёсткий отсев явно чужих FE-секций при узком запросе."""
    if not _query_wants_frontend_composite(query):
        return False
    if _heading_is_nfr_support(chunk.heading):
        return True
    wants_detail = _query_wants_detail_card(query)
    wants_feed = _query_wants_feed_screen(query)
    if wants_detail and not wants_feed:
        if _source_is_feed_fe(chunk.source):
            return True
        if _source_is_cancel_fe(chunk.source) and not _query_wants_cancel(query):
            return True
    if wants_feed and not wants_detail and _source_is_detail_fe(chunk.source):
        return True
    return False
