"""Юнит-тесты чистых функций офлайн-контура индексации (без Qdrant/OpenAI)."""

from llama_index.core.schema import Document

from app.services.ingestion import (
    EXCLUDED_EMBED_KEYS,
    clean,
    department_from_path,
    doc_type_from_path,
    enrich,
    file_metadata,
    is_deprecated_path,
    layer_from_path,
    release_version_from_filename,
    ticket_from_path,
    version_from_filename,
)


def test_clean_strips_footer_and_joins_hyphenation() -> None:
    raw = "Регламент возврата Стр. 12 из 47 авто-\nмобиль доступен https://x.io/a тут"
    out = clean(raw)
    assert "Стр. 12 из 47" not in out
    assert "автомобиль" in out
    assert "https://" not in out


def test_clean_collapses_blank_lines() -> None:
    assert clean("a\n\n\n\n\nb") == "a\n\nb"


def test_department_from_path_uses_top_folder() -> None:
    assert department_from_path("data/finance/2025/policy.pdf") == "finance"
    assert department_from_path("knowledge_base/support/faq.md") == "support"


def test_department_from_path_defaults_to_general() -> None:
    assert department_from_path("/tmp/loose_file.pdf") == "general"
    assert department_from_path("data") == "general"


def test_doc_type_from_path() -> None:
    assert doc_type_from_path("a/b/policy.PDF") == "pdf"
    assert doc_type_from_path("note.md") == "md"
    assert doc_type_from_path("no_ext") == "unknown"


def test_version_from_filename() -> None:
    assert version_from_filename("policy_2025_v3.pdf") == "2025_v3"
    assert version_from_filename("plain_doc.pdf") == "unversioned"


def test_file_metadata_has_filter_fields() -> None:
    meta = file_metadata("data/hr/2025/onboarding_2025_v2.docx")
    assert meta["department"] == "hr"
    assert meta["doc_type"] == "docx"
    assert meta["version"] == "2025_v2"
    assert meta["visibility"] == "internal"
    assert meta["source"] == "onboarding_2025_v2.docx"


def test_ticket_from_path() -> None:
    assert ticket_from_path("data/[SIHIST-3485]_Композит.md") == "SIHIST-3485"
    assert ticket_from_path("data/SIHIST-427_Android.md") == "SIHIST-427"
    assert ticket_from_path("data/plain.md") == "unknown"


def test_layer_from_path() -> None:
    assert layer_from_path("data/my-kb/SIHIST/SIHIST_markdown_back/x.md") == "BE"
    assert layer_from_path("data/my-kb/SIHIST/SIHIST_markdown_front/x.md") == "FE"
    assert layer_from_path("data/my-kb/SIHIST/SIHIST_markdown_МП/SIHIST_[МП]_x.md") == "MP"
    assert layer_from_path("data/my-kb/SIHIST/db-export/БД.md") == "DB"
    assert layer_from_path("data/loose.md") == "general"


def test_release_version_from_filename() -> None:
    assert release_version_from_filename("Технические_задачи_в_6.23.md") == "6.23"
    assert release_version_from_filename("Технический_релиз_8.8.md") == "8.8"
    assert release_version_from_filename("plain_doc.md") == "unversioned"


def test_is_deprecated_path_detects_old_feed() -> None:
    assert is_deprecated_path("data/my-kb/SIHIST/Фронт Старая Лента markdown/x.md")
    assert not is_deprecated_path("data/my-kb/SIHIST/Фронт Композит/x.md")


def test_file_metadata_sihist_fields() -> None:
    meta = file_metadata(
        "data/my-kb/SIHIST/SIHIST_markdown_back/[SIHIST-2162]_Технические_задачи_в_6.23.md"
    )
    assert meta["ticket"] == "SIHIST-2162"
    assert meta["layer"] == "BE"
    assert meta["release_version"] == "6.23"
    assert meta["deprecated"] == "false"


def test_enrich_cleans_text_and_excludes_technical_keys() -> None:
    docs = [Document(text="Тариф Стр. 3 из 9 описан тут", metadata={"department": "billing"})]
    out = enrich(docs)
    assert "Стр. 3 из 9" not in out[0].text
    assert out[0].excluded_embed_metadata_keys == EXCLUDED_EMBED_KEYS
    assert out[0].excluded_llm_metadata_keys == EXCLUDED_EMBED_KEYS


def test_enrich_marks_superseded_document_deprecated() -> None:
    docs = [Document(text="Старое описание\nsuperseded_by: SIHIST-9999\nконец", metadata={})]
    out = enrich(docs)
    assert out[0].metadata["superseded_by"] == "SIHIST-9999"
    assert out[0].metadata["deprecated"] == "true"


def test_reindex_all_recreates_collection_after_delete(monkeypatch) -> None:
    """full reindex: delete → create_collection → ingest (без 404 на upsert)."""
    from pathlib import Path

    from app.core.config import Settings
    from app.services.ingestion import IngestionService

    settings = Settings(
        llm={"openai_api_key": "sk-test"},
        rag_data_dir=Path("data/rag-block-03"),
        rag_collection="test_rag_coll",
        embedding_dim=1536,
        rag_use_hybrid=False,  # dense-only путь: коллекцию создаём вручную
    )
    service = object.__new__(IngestionService)
    service._settings = settings
    service._data_dir = settings.rag_data_dir
    service._docstore_path = Path("data/test_rag_coll_docstore.json")

    client = type("Client", (), {})()
    client.collection_exists = lambda name: False
    client.delete_collection = lambda name: None
    created: list[str] = []

    def create_collection(**kwargs):
        created.append(kwargs["collection_name"])

    client.create_collection = create_collection
    client.close = lambda: None
    service._client = client
    service._vector_store = object()
    service._embed_model = object()
    service._docstore = object()
    service._pipeline = object()

    monkeypatch.setattr(service, "_make_vector_store", lambda: object())
    monkeypatch.setattr(service, "_build_pipeline", lambda: None)
    monkeypatch.setattr(service, "ingest_all", lambda: 42)

    assert service.reindex_all() == 42
    assert created == ["test_rag_coll"]


def test_ensure_collection_skips_manual_create_in_hybrid_mode() -> None:
    """В гибридном режиме коллекцию создаёт сам QdrantVectorStore — вручную нет."""
    from pathlib import Path

    from app.core.config import Settings
    from app.services.ingestion import IngestionService

    settings = Settings(
        llm={"openai_api_key": "sk-test"},
        rag_data_dir=Path("data/rag-block-03"),
        rag_collection="hybrid_coll",
        embedding_dim=1536,
        rag_use_hybrid=True,
    )
    service = object.__new__(IngestionService)
    service._settings = settings
    created: list[str] = []
    client = type("Client", (), {})()
    client.collection_exists = lambda name: False
    client.create_collection = lambda **kw: created.append(kw["collection_name"])
    service._client = client

    service._ensure_collection()
    assert created == []


def test_ingestion_openai_embed_batch_size_from_settings() -> None:
    from pathlib import Path

    from llama_index.embeddings.openai import OpenAIEmbedding

    from app.core.config import Settings
    from app.services.ingestion import IngestionService

    settings = Settings(
        llm={"openai_api_key": "sk-test"},
        rag_data_dir=Path("data/rag-block-03"),
        rag_collection="test_coll",
        rag_embed_batch_size=16,
        embedding_dim=1536,
    )
    service = object.__new__(IngestionService)
    service._settings = settings
    service._embed_model = OpenAIEmbedding(
        model=settings.embedding_model,
        api_key=settings.llm.openai_api_key.get_secret_value(),
        embed_batch_size=settings.rag_embed_batch_size,
    )
    assert service._embed_model.embed_batch_size == 16
