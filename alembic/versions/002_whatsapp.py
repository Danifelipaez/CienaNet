"""WhatsApp layer: users, conversations, catch_reports, alert_log.

Revision ID: 002
Revises: 001
Create Date: 2026-06-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wa_id", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=True),
        sa.Column("comunidad", sa.String(100), nullable=True),
        sa.Column("alertas_activas", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wa_id"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("message_type", sa.String(20), server_default=sa.text("'text'"), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("wa_message_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_id_created_at", "conversations", ["user_id", "created_at"])

    op.create_table(
        "catch_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # fishing_point_id: sin FK todavía — la tabla fishing_points se crea en 003,
        # que agrega la ForeignKeyConstraint.
        sa.Column("fishing_point_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("especie", sa.String(50), nullable=True),
        sa.Column("cantidad_indice", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catch_reports_timestamp", "catch_reports", ["timestamp"])

    op.create_table(
        "alert_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("color", sa.String(10), nullable=False),
        sa.Column("zonas", sa.Text(), nullable=True),
        sa.Column("canal", sa.String(20), server_default=sa.text("'whatsapp'"), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("destinatarios_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_log_created_at", "alert_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("alert_log")
    op.drop_index("ix_catch_reports_timestamp", "catch_reports")
    op.drop_table("catch_reports")
    op.drop_index("ix_conversations_user_id_created_at", "conversations")
    op.drop_table("conversations")
    op.drop_table("users")
