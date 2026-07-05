"""AI conversations por usuario: columna user_id para hilo/historial por sesión.

Revision ID: 007
Revises: 006
Create Date: 2026-07-02

La vista 'Pregunta a la IA' es multiusuario (varios miembros del equipo, incluso
simultáneos). Cada cliente genera un UUID en localStorage y lo envía como
X-User-Id; se persiste aquí para aislar hilo (memoria) e historial por usuario.
Identidad blanda para scoping, no control de acceso — ese sigue siendo ADMIN_API_KEY.

Filas previas (sin usuario) reciben 'legacy' vía server_default para no romper la
columna NOT NULL en una tabla ya poblada.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_conversations",
        sa.Column("user_id", sa.String(64), server_default=sa.text("'legacy'"), nullable=False),
    )
    op.create_index(
        "ix_ai_conversations_user_id_created_at", "ai_conversations", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_conversations_user_id_created_at", "ai_conversations")
    op.drop_column("ai_conversations", "user_id")
