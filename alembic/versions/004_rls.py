"""Enable RLS (sin políticas) en las tablas nuevas del schema public.

Revision ID: 004
Revises: 003
Create Date: 2026-06-30

Supabase expone el schema `public` vía su Data API (PostgREST) con grants por
defecto a los roles anon/authenticated. `users` guarda teléfonos (wa_id) y
`conversations` guarda contenido de mensajes — sin RLS quedarían accesibles
sin autenticación. El backend usa una connection string directa a Postgres
(rol con BYPASSRLS), así que habilitar RLS sin políticas (deny-all para
anon/authenticated) no afecta al backend.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["users", "conversations", "catch_reports", "alert_log", "fishing_points"]


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
