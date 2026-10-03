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
    r"|(?:[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+)\b"
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


def _parse_markdown_chunks(path: Path, content: str) -> list[DocChunk]:
    content = _strip_front_matter(content)
    relative = path.name

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
        chunks.extend(_parse_markdown_chunks(path, path.read_text(encoding="utf-8")))
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


def _chunk_has_contract_body(text: str) -> bool:
    """Есть ли в чанке реальный контракт (JSON/таблица полей), а не титул/сценарий."""
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
            '"agreements"',
            '"linkedevents"',
            '"generalstatus"',
            '"totaldeals"',
            '"commissions"',
            "generalstatus|",
            "totaldeals|",
            "linkedevents|",
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


def _contract_field_richness(text: str) -> int:
    low = (text or "").lower()
    keys = (
        "generalstatus",
        "totaldeals",
        "agreements",
        "linkedevents",
        "commissions",
        "pagesize",
        "operationdate",
    )
    return sum(1 for key in keys if key in low)


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


def _clip_contract_window(
    text: str,
    *,
    api_ids: list[str] | None = None,
    query: str = "",
    limit: int = _MAX_CHUNK_CHARS,
) -> str:
    """Для больших секций вырезает окно вокруг JSON/таблицы/API, не «шапку» JIRA."""
    if len(text) <= limit:
        return text

    low = text.lower()
    anchors: list[int] = []

    for marker in (
        "```json",
        "параметры ответа",
        "параметры запроса",
        "пример ответа",
        "пример запроса",
        "описание ответа",
        "описание запроса",
        '"generalstatus"',
        '"totaldeals"',
        '"agreements"',
        '"linkedevents"',
        '"commissions"',
    ):
        pos = low.find(marker)
        if pos >= 0:
            anchors.append(pos)

    for api in api_ids or []:
        key = _normalize_api_key(api)
        # грубый поиск нормализованного API в тексте
        compact = re.sub(r"[^a-z0-9]", "", low)
        idx = compact.find(key)
        if idx >= 0:
            # приблизительная позиция в исходном тексте
            anchors.append(min(len(text) - 1, idx))

    for token in _tokenize(query):
        if len(token) < 5:
            continue
        pos = low.find(token)
        if pos >= 0:
            anchors.append(pos)

    if not anchors:
        return _clip(text, limit)

    start = max(0, min(anchors) - 400)
    end = min(len(text), start + limit)
    if end - start < limit:
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
        wants_contract = any(
            token in query.lower()
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
            )
        ) or bool(api_ids)

        scored: list[tuple[int, DocChunk]] = []
        for chunk in self._chunks:
            score = self._score_chunk(chunk, query_tokens, api_ids, wants_contract)
            if score > 0:
                scored.append((score, chunk))

        if not scored:
            return f"Ничего не найдено по запросу: {query}"

        scored.sort(key=lambda item: item[0], reverse=True)

        # Контрактные секции из файлов с именем обмена — всегда в начале.
        # Важно: не титул/«Содержание»/JIRA-мета, а чанки с JSON/таблицами полей.
        forced: list[DocChunk] = []
        seen: set[str] = set()
        if api_ids:
            candidates: list[DocChunk] = []
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
                # В forced — только реальные контракты или явные contract-heading.
                # Титул файла с API без тела больше не форсим.
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
            forced = candidates

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
            selected.append(chunk)
            seen.add(key)
            if len(selected) >= _TOP_K:
                break

        parts: list[str] = []
        total = 0
        for index, chunk in enumerate(selected, start=1):
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

        header = f"Найдено {len(parts)} фрагментов по запросу «{query}»"
        if api_ids:
            header += f" (API: {', '.join(api_ids[:4])})"
        if forced:
            header += f"; контрактных секций: {len(forced)}"
        return header + ":\n\n" + "\n\n".join(parts)

    @staticmethod
    def _score_chunk(
        chunk: DocChunk,
        query_tokens: set[str],
        api_ids: list[str],
        wants_contract: bool,
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

        # Огромные «простыни» без API в имени — слабее.
        if len(chunk.text) > 20_000 and not (api_ids and _source_matches_api(chunk.source, api_ids)):
            score -= 10

        return score
