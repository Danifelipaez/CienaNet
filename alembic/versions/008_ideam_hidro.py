"""IDEAM hidro readings: respaldo propio de precipitación/nivel de río en vivo.

Revision ID: 008
Revises: 007
Create Date: 2026-07-06

Ver app/services/ingestion/ideam_hidro.py y docs/IDEAM_GBIF_VALIDACION.md: la API
Socrata de IDEAM ya retiene el histórico completo, así que esta tabla no es la
fuente de /data/history (que sigue leyendo en vivo) — es un respaldo que el cron
diario (GET /data/latest) va acumulando, por si la API pública de datos.gov.co
cambia o deja de estar disponible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ideam_hidro_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("variable", sa.String(30), nullable=False),
        sa.Column("estacion", sa.String(100), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variable", "estacion", "date", name="uq_ideam_hidro_variable_estacion_date"),
    )
    op.execute("ALTER TABLE ideam_hidro_readings ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("ideam_hidro_readings")
