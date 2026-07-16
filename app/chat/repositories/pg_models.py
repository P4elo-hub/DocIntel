import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ChatRow(Base):
    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_external_id: Mapped[str] = mapped_column(Text, nullable=False)
    interface: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index(
            "ix_chat_messages_chat_created",
            "chat_id",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    media_refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Цитаты RAG-ответа, показанные пользователю: по ним отрицательная оценка
    # указывает, что чинить (плохие источники → поиск, хорошие но плохой ответ → генерация).
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RagQueryRow(Base):
    """Лог RAG-запросов для аналитики: refusal_rate и пробелы в знаниях.

    Пишет RAG-роут (/rag/query), читает AdminRepository (refusal_rate,
    knowledge_gaps).
    """

    __tablename__ = "rag_queries"
    __table_args__ = (
        Index(
            "idx_rag_queries_confident_created",
            "confident",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    confident: Mapped[bool] = mapped_column(nullable=False)
    top_score: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SystemPromptRow(Base):
    __tablename__ = "system_prompts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(default=False)
    traffic_pct: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
