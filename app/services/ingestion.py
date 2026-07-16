"""Офлайн-контур RAG: парсинг корпуса, обогащение метаданными и индексация.

Индексация вынесена из онлайн-запроса: `IngestionPipeline` с
`DocstoreStrategy.UPSERTS` и docstore, который сохраняется на диск, поэтому
повторный прогон обновляет только изменённые документы, а не переэмбеддит весь
корпус. Запись идёт в ту же коллекцию Qdrant, из которой читает `RAGService`.

Чистые функции (`clean`, `enrich`, `*_from_path`) не зависят от внешних
сервисов и покрыты юнит-тестами; класс `IngestionService` ходит в Qdrant и
OpenAI и проверяется в `scripts/verify_rag.py` на живых сервисах.
"""

import logging
import re
from datetime import date
from pathlib import Path

from llama_index.core import SimpleDirectoryReader
from llama_index.core.ingestion import DocstoreStrategy, IngestionPipeline
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import Document
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, HnswConfigDiff, VectorParams

from app.core.config import Settings as AppSettings

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = [".pdf", ".docx", ".md", ".txt", ".html"]

# Технические поля не несут смысла для эмбеддинга — они нужны только как фильтры
# и для отображения источника. Если их не исключить, LlamaIndex подмешает их в
# текст ноды и зашумит вектор.
EXCLUDED_EMBED_KEYS = [
    "file_path",
    "file_name",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "doc_type",
    "version",
    "visibility",
    "indexed_at",
    "ticket",
    "layer",
    "release_version",
    "deprecated",
    "superseded_by",
]

# Папки/маркеры устаревшего контента: индексировать их не нужно, чтобы модель не
# отвечала по старым экранам («Старая Лента» заменена «Композитом»).
_DEPRECATED_PATH_MARKERS = ("Старая Лента", "Старая лента", "старая лента")

# Маркер ручной дедупликации в теле документа: строка вида
#   superseded_by: SIHIST-1234   (или <!-- superseded_by: SIHIST-1234 -->)
# помечает фичу как замещённую другой — такой документ считается устаревшим.
_SUPERSEDED_RE = re.compile(r"superseded_by:\s*(SIHIST-\d+)", re.IGNORECASE)

_TICKET_RE = re.compile(r"SIHIST-\d+", re.IGNORECASE)
# Версия релиза в имени файла: «Технические задачи в 6.23», «...8.8» и т.п.
# Без \b: перед номером часто стоит «_» (тоже word-символ) — берём lookaround по цифрам.
_RELEASE_RE = re.compile(r"(?<!\d)(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?!\d)")


def clean(text: str) -> str:
    """Снимает типичный шум PDF-экспорта перед чанкингом.

    Колонтитулы и номера страниц попадают в каждый чанк и зашумляют эмбеддинг;
    перенос слова по дефису на конце строки рвёт токен («авто-\\nмобиль»).
    """
    text = re.sub(r"Стр\.\s*\d+\s*из\s*\d+", "", text)
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"https?://\S+", "", text)
    return text.strip()


def department_from_path(path: str) -> str:
    """`data/finance/2025/policy.pdf` -> `finance` (папка верхнего уровня корпуса)."""
    parts = Path(path).parts
    for anchor in ("knowledge_base", "data"):
        if anchor in parts:
            idx = parts.index(anchor)
            return parts[idx + 1] if len(parts) > idx + 1 else "general"
    return "general"


def doc_type_from_path(path: str) -> str:
    """Тип документа из расширения файла: `pdf`, `docx`, `md`, ..."""
    return Path(path).suffix.lstrip(".").lower() or "unknown"


def version_from_filename(path: str) -> str:
    """`policy_2025_v3.pdf` -> `2025_v3`; если версии нет — `unversioned`."""
    match = re.search(r"(20\d{2}(?:[_-]v?\d+)?)", Path(path).stem)
    return match.group(1) if match else "unversioned"


def ticket_from_path(path: str) -> str:
    """Номер задачи из имени файла: `[SIHIST-3485]_...` -> `SIHIST-3485`."""
    match = _TICKET_RE.search(Path(path).name)
    return match.group(0).upper() if match else "unknown"


def layer_from_path(path: str) -> str:
    """Слой продукта из пути: BE / FE / MP / DB / general."""
    lowered = str(path).lower()
    if "markdown_back" in lowered or "/back" in lowered:
        return "BE"
    if "markdown_front" in lowered or "/front" in lowered:
        return "FE"
    if "markdown_мп" in lowered or "_[мп]" in lowered or "[мп]" in lowered:
        return "MP"
    if "db-export" in lowered or "/db" in lowered:
        return "DB"
    return "general"


def release_version_from_filename(path: str) -> str:
    """Версия релиза из имени: «Технические задачи в 6.23» -> `6.23`.

    Отдаёт последнюю подходящую группу вида X.Y[.Z]; если версии нет — `unversioned`.
    """
    matches = _RELEASE_RE.findall(Path(path).stem)
    return matches[-1] if matches else "unversioned"


def is_deprecated_path(path: str) -> bool:
    """Путь относится к устаревшему контенту (например, «Старая Лента»)."""
    return any(marker in str(path) for marker in _DEPRECATED_PATH_MARKERS)


def file_metadata(path: str) -> dict[str, str]:
    """Хук `SimpleDirectoryReader.file_metadata`: метаданные на этапе загрузки."""
    return {
        "source": Path(path).name,
        "department": department_from_path(path),
        "doc_type": doc_type_from_path(path),
        "version": version_from_filename(path),
        "ticket": ticket_from_path(path),
        "layer": layer_from_path(path),
        "release_version": release_version_from_filename(path),
        "deprecated": str(is_deprecated_path(path)).lower(),
        "visibility": "internal",
        "indexed_at": date.today().isoformat(),
    }


def enrich(documents: list[Document]) -> list[Document]:
    """Чистит текст и помечает технические поля исключёнными из эмбеддинга.

    Метаданные из путей уже проставлены `file_metadata` на загрузке; здесь —
    финальная нормализация документа, разбор маркера дедупликации
    `superseded_by:` в теле и пометка технических полей перед чанкингом.
    """
    for doc in documents:
        text = doc.text
        superseded = _SUPERSEDED_RE.search(text)
        if superseded:
            doc.metadata["superseded_by"] = superseded.group(1).upper()
            # Замещённая другой задачей фича — устаревшая.
            doc.metadata["deprecated"] = "true"
        # Document.text — read-only property поверх text_resource, пишем через set_content.
        doc.set_content(clean(text))
        doc.excluded_embed_metadata_keys = EXCLUDED_EMBED_KEYS
        doc.excluded_llm_metadata_keys = EXCLUDED_EMBED_KEYS
    return documents


def _is_deprecated_doc(doc: Document) -> bool:
    return str(doc.metadata.get("deprecated", "")).lower() == "true"


class IngestionService:
    """Индексатор корпуса: один экземпляр на процесс, переиспользует пайплайн.

    Docstore сохраняется на диск (`docstore_path`), что делает `UPSERTS`
    идемпотентным между запусками: неизменённые документы пропускаются.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        api_key = settings.llm.openai_api_key.get_secret_value()
        qdrant_key = (
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        )
        self._data_dir = Path(settings.rag_data_dir)
        self._docstore_path = self._data_dir.parent / f"{settings.rag_collection}_docstore.json"

        self._client = QdrantClient(url=settings.qdrant_url, api_key=qdrant_key)
        self._vector_store = self._make_vector_store()
        self._embed_model = OpenAIEmbedding(
            model=settings.embedding_model,
            api_key=api_key,
            embed_batch_size=settings.rag_embed_batch_size,
        )
        self._docstore = self._load_docstore()
        self._pipeline = self._build_pipeline()

    @property
    def docstore_path(self) -> Path:
        """Путь к сохранённому docstore — состояние инкрементальной индексации."""
        return self._docstore_path

    def _make_vector_store(self) -> QdrantVectorStore:
        """Хранилище для записи нод. В гибридном режиме включаем sparse-вектора
        (fastembed BM25), иначе поиск hybrid в rag.py не найдёт разреженную часть."""
        kwargs: dict = {
            "client": self._client,
            "collection_name": self._settings.rag_collection,
        }
        if self._settings.rag_use_hybrid:
            kwargs["enable_hybrid"] = True
            kwargs["fastembed_sparse_model"] = self._settings.rag_sparse_model
        return QdrantVectorStore(**kwargs)

    def _node_transformations(self) -> list:
        """Разбиение документа на ноды перед эмбеддингом.

        При `rag_chunk_by_headings` сначала режем markdown по заголовкам
        (раздел фичи AS IS / TO BE / Интеграции остаётся цельным чанком с
        путём заголовков в метаданных), затем ограничиваем размер слишком
        крупных разделов `SentenceSplitter`. Иначе — только по предложениям.
        """
        splitter = SentenceSplitter(
            chunk_size=self._settings.rag_chunk_size,
            chunk_overlap=self._settings.rag_chunk_overlap,
        )
        if self._settings.rag_chunk_by_headings:
            return [MarkdownNodeParser(), splitter]
        return [splitter]

    def _build_pipeline(self) -> IngestionPipeline:
        return IngestionPipeline(
            transformations=[*self._node_transformations(), self._embed_model],
            docstore=self._docstore,
            vector_store=self._vector_store,
            docstore_strategy=DocstoreStrategy.UPSERTS,
        )

    def _load_docstore(self) -> SimpleDocumentStore:
        if self._docstore_path.exists():
            return SimpleDocumentStore.from_persist_path(str(self._docstore_path))
        return SimpleDocumentStore()

    def is_collection_empty(self) -> bool:
        """Коллекции нет или она пуста — значит нужна первичная индексация."""
        if not self._client.collection_exists(self._settings.rag_collection):
            return True
        return self._client.count(self._settings.rag_collection).count == 0

    def _ensure_collection(self) -> None:
        """Создаёт коллекцию Qdrant, если её нет (после delete или первого прогона).

        LlamaIndex upsert'ит в уже существующую коллекцию и сам её не создаёт
        после явного delete_collection — поэтому full reindex обязан вызвать это.
        """
        if self._client.collection_exists(self._settings.rag_collection):
            return
        # В гибридном режиме коллекцию с dense+sparse векторами создаёт сам
        # QdrantVectorStore при первом upsert (имена векторов зависят от версии
        # интеграции) — вручную dense-only коллекцию создавать нельзя.
        if self._settings.rag_use_hybrid:
            return
        self._client.create_collection(
            collection_name=self._settings.rag_collection,
            vectors_config=VectorParams(
                size=self._settings.embedding_dim,
                distance=Distance.COSINE,
            ),
            hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
        )
        logger.info(
            "ingestion: создана коллекция %s (dim=%d)",
            self._settings.rag_collection,
            self._settings.embedding_dim,
        )

    def _persist_docstore(self) -> None:
        self._docstore_path.parent.mkdir(parents=True, exist_ok=True)
        self._docstore.persist(str(self._docstore_path))

    def _read(self, *, input_files: list[Path] | None = None) -> list[Document]:
        reader = SimpleDirectoryReader(
            input_dir=str(self._data_dir) if input_files is None else None,
            input_files=[str(p) for p in input_files] if input_files else None,
            recursive=input_files is None,
            required_exts=SUPPORTED_EXTS,
            file_metadata=file_metadata,
            filename_as_id=True,
        )
        documents = enrich(reader.load_data())
        if self._settings.rag_skip_deprecated:
            kept = [d for d in documents if not _is_deprecated_doc(d)]
            skipped = len(documents) - len(kept)
            if skipped:
                logger.info("ingestion: пропущено устаревших документов=%d", skipped)
            return kept
        return documents

    def ingest_all(self) -> int:
        """Полная переиндексация корпуса. UPSERTS пропустит неизменённое."""
        self._ensure_collection()
        documents = self._read()
        batch_size = max(1, self._settings.rag_ingest_doc_batch_size)
        total_nodes = 0
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            nodes = self._pipeline.run(documents=batch, show_progress=False)
            total_nodes += len(nodes)
            self._persist_docstore()
            logger.info(
                "ingestion: пакет %d–%d/%d документов, нод=%d (всего нод=%d)",
                start + 1,
                start + len(batch),
                len(documents),
                len(nodes),
                total_nodes,
            )
        logger.info(
            "ingestion: корпус проиндексирован, документов=%d нод=%d",
            len(documents),
            total_nodes,
        )
        return total_nodes

    def ingest_files(self, paths: list[str]) -> int:
        """Точечная индексация перечисленных файлов (webhook документооборота)."""
        files = [Path(p) for p in paths if Path(p).exists()]
        if not files:
            return 0
        documents = self._read(input_files=files)
        nodes = self._pipeline.run(documents=documents, show_progress=False)
        self._persist_docstore()
        logger.info("ingestion: точечно проиндексировано файлов=%d нод=%d", len(files), len(nodes))
        return len(nodes)

    def reindex_all(self) -> int:
        """Полная переиндексация: вычищаем коллекцию и docstore, строим заново.

        Нужна после смены схемы метаданных или модели эмбеддингов, когда
        инкрементальный UPSERTS по хешам уже не отражает реальное состояние.
        """
        if self._client.collection_exists(self._settings.rag_collection):
            self._client.delete_collection(self._settings.rag_collection)
        self._docstore = SimpleDocumentStore()
        self._docstore_path.unlink(missing_ok=True)
        # Пересоздаём store: его внутренний флаг «коллекция существует» после
        # внешнего delete_collection иначе останется взведён и upsert даст 404.
        self._vector_store = self._make_vector_store()
        self._pipeline = self._build_pipeline()
        self._ensure_collection()
        logger.info("ingestion: полная переиндексация коллекции %s", self._settings.rag_collection)
        return self.ingest_all()

    def run_for_file(self, path: Path) -> int:
        """Индексация одного загруженного файла. Упавший файл изолируется в `.failed`."""
        try:
            count = self.ingest_files([str(path)])
            logger.info("ingestion: файл проиндексирован file=%s нод=%d", path.name, count)
            return count
        except Exception:
            logger.exception("ingestion: файл не проиндексирован file=%s", path.name)
            path.rename(path.with_suffix(path.suffix + ".failed"))
            return 0

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            logger.debug("ошибка при закрытии Qdrant-клиента ingestion", exc_info=True)
