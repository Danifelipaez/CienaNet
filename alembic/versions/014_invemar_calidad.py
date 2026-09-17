"""INVEMAR calidad de agua: condición vigente por estación (REDCAM).

Revision ID: 014
Revises: 013
Create Date: 2026-09-15

Ver app/services/ingestion/invemar_calidad.py. Un row por (estacion, variable),
sobreescrito en cada refresco (upsert) — no es serie histórica como
ideam_hidro_readings: el dato de origen ya es "condición vigente más reciente".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invemar_calidad_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("estacion", sa.String(100), nullable=False),
        sa.Column("sector", sa.String(150), nullable=True),
        sa.Column("variable", sa.String(50), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("unidad", sa.String(20), nullable=True),
        sa.Column("clase", sa.Integer(), nullable=True),
        sa.Column("rango", sa.String(50), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("fuente_actualizado", sa.String(30), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("estacion", "variable", name="uq_invemar_calidad_estacion_variable"),
    )
    op.execute("ALTER TABLE invemar_calidad_readings ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("invemar_calidad_readings")
