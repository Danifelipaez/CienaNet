"""AI conversations: historial de la vista 'Pregunta a la IA' del dashboard.

Revision ID: 006
Revises: 005
Create Date: 2026-06-30

Independiente de `conversations` (WhatsApp) — uso interno admin.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pregunta", sa.Text(), nullable=False),
        sa.Column("respuesta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sugerencia", sa.Text(), nullable=True),
        sa.Column("contexto", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("ALTER TABLE ai_conversations ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("ai_conversations")
