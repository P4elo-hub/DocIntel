"""bot production tables: media_refs, feedback, rate-limit, alerts

Revision ID: 002_bot_production
Revises: 001_chat_tables
Create Date: 2026-07-15 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002_bot_production"
down_revision: Union[str, None] = "001_chat_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("media_refs", JSONB(), nullable=True),
    )
    op.add_column(
        "chat_messages",
        sa.Column("prompt_id", UUID(as_uuid=True), nullable=True),
    )

    op.create_table(
        "system_prompts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "traffic_pct",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_chat_messages_prompt_id",
        source_table="chat_messages",
        referent_table="system_prompts",
        local_cols=["prompt_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "chats",
        sa.Column(
            "handoff_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )

    op.create_table(
        "rate_limits",
        sa.Column("owner_external_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column(
            "count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint(
            "owner_external_id",
            "kind",
            "bucket",
            name="pk_rate_limits",
        ),
    )
    op.create_index(
        "idx_rate_limits_bucket",
        "rate_limits",
        ["bucket"],
    )

    op.create_table(
        "message_feedback",
        sa.Column("message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("owner_external_id", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint(
            "owner_external_id",
            "message_id",
            name="pk_message_feedback",
        ),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("acked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("total_owners", sa.Integer(), nullable=False),
        sa.Column(
            "sent", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "failed", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("last_owner_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("broadcasts")
    op.drop_table("alerts")
    op.drop_table("message_feedback")
    op.drop_index("idx_rate_limits_bucket", table_name="rate_limits")
    op.drop_table("rate_limits")
    op.drop_column("chats", "handoff_status")
    op.drop_constraint(
        "fk_chat_messages_prompt_id", "chat_messages", type_="foreignkey"
    )
    op.drop_table("system_prompts")
    op.drop_column("chat_messages", "prompt_id")
    op.drop_column("chat_messages", "media_refs")
