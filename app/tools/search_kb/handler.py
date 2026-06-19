"""Handler: поиск по проектной документации."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zа-яё0-9]+", text.lower()) if len(token) > 2}


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


class SearchKbHandler:
    def __init__(
        self,
        knowledge_base_path: Path | None = None,
        docs_dir: Path | None = None,
    ) -> None:
        self._chunks: list[DocChunk] = []

        if docs_dir is not None:
            self._chunks.extend(_load_docs_chunks(docs_dir))

        if knowledge_base_path is not None:
            self._chunks.extend(_load_txt_chunks(knowledge_base_path))

    def search_kb(self, query: str) -> str:
        query = query.strip()
        if not query:
            return "Ничего не найдено: пустой запрос."

        if not self._chunks:
            return "База документации пуста. Добавьте .md файлы в app/data/docs/ или записи в knowledge_base.txt."

        query_tokens = _tokenize(query)
        if not query_tokens:
            return "Ничего не найдено: укажите ключевые слова."

        scored: list[tuple[int, DocChunk]] = []
        for chunk in self._chunks:
            overlap = len(query_tokens & _tokenize(chunk.text))
            if overlap:
                scored.append((overlap, chunk))

        if not scored:
            return f"Ничего не найдено по запросу: {query}"

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:5]
        body = "\n\n".join(
            f"{index}. {chunk.label}\n{chunk.text}"
            for index, (_, chunk) in enumerate(top, start=1)
        )
        return f"Найдено {len(top)} фрагментов по запросу «{query}»:\n\n{body}"
