"""rag analytics: лог запросов и источники у сообщений ассистента

Добавляем:
- rag_queries — лог RAG-запросов (refusal_rate и пробелы в знаниях)
- chat_messages.sources — цитаты RAG-ответа рядом с сообщением ассистента,
  чтобы 👎 по message_id указывал, что чинить (поиск или генерацию)

Revision ID: 003_rag_analytics
Revises: 002_bot_production
Create Date: 2026-07-16 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003_rag_analytics"
down_revision: Union[str, None] = "002_bot_production"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_queries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("question_normalized", sa.Text(), nullable=False),
        sa.Column("confident", sa.Boolean(), nullable=False),
        sa.Column("top_score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Покрывает и refusal_rate за окно, и группировку пробелов по неуверенным ответам.
    op.create_index(
        "idx_rag_queries_confident_created",
        "rag_queries",
        ["confident", "created_at"],
    )
    op.add_column("chat_messages", sa.Column("sources", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "sources")
    op.drop_index("idx_rag_queries_confident_created", table_name="rag_queries")
    op.drop_table("rag_queries")
