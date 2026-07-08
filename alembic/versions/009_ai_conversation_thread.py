"""AI conversations agrupadas en hilos: columna conversation_id.

Revision ID: 009
Revises: 008
Create Date: 2026-07-08

Hasta ahora cada fila de ai_conversations era un turno suelto y la vista IA lo
pintaba como una tarjeta de historial independiente. Las grandes plataformas de
chat agrupan los turnos en conversaciones (un hilo = una tarjeta). conversation_id
es esa clave de agrupación: todos los turnos de un mismo hilo la comparten.

Filas previas (sin hilo) reciben conversation_id = id, es decir, cada turno viejo
pasa a ser su propia conversación de un solo mensaje — no se pierde nada ni se
mezclan preguntas de distintos momentos.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_conversations",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Backfill: cada turno preexistente es su propia conversación de un solo mensaje.
    op.execute("UPDATE ai_conversations SET conversation_id = id WHERE conversation_id IS NULL")
    op.alter_column("ai_conversations", "conversation_id", nullable=False)
    op.create_index(
        "ix_ai_conversations_user_conv_created",
        "ai_conversations",
        ["user_id", "conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_conversations_user_conv_created", "ai_conversations")
    op.drop_column("ai_conversations", "conversation_id")
