"""Sedimentation zones: capa de polígonos para la vista Mapa.

Revision ID: 005
Revises: 004
Create Date: 2026-06-30

Polígonos aproximados a partir de las zonas con sedimentación reportada en
las observaciones de fishing_points (Los Muertos, Santa Rosa) — pendiente de
validar con el equipo territorial. Ajustar libremente sin nueva migración:
son datos, no esquema (mismo criterio que 003_fishing_points).
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ZONES = [
    {
        "nombre": "Caño de Los Muertos",
        "nivel": "alto",
        "observacion": "Sedimento en suspensión persistente tras temporada de lluvias.",
        "polygon": [
            [10.760, -74.458], [10.752, -74.451], [10.745, -74.456], [10.749, -74.466], [10.760, -74.458],
        ],
    },
    {
        "nombre": "Caño Santa Rosa",
        "nivel": "alto",
        "observacion": "Sedimentación crítica, acceso reducido para embarcaciones.",
        "polygon": [
            [10.815, -74.348], [10.808, -74.341], [10.800, -74.346], [10.804, -74.355], [10.815, -74.348],
        ],
    },
    {
        "nombre": "Entrada Caño Grande",
        "nivel": "medio",
        "observacion": "Sedimentación moderada en la desembocadura, varía con el caudal del río.",
        "polygon": [
            [10.800, -74.405], [10.794, -74.398], [10.787, -74.403], [10.791, -74.412], [10.800, -74.405],
        ],
    },
]


def upgrade() -> None:
    op.create_table(
        "sedimentation_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("polygon", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("nivel", sa.String(10), nullable=False),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # CAST(...AS jsonb) sobre parámetro string: igual que 003_fishing_points,
    # bulk_insert con columna JSONB no renderiza en modo offline.
    insert_stmt = sa.text(
        "INSERT INTO sedimentation_zones (nombre, polygon, nivel, observacion) "
        "VALUES (:nombre, CAST(:polygon AS jsonb), :nivel, :observacion)"
    )
    for z in _ZONES:
        op.execute(
            insert_stmt.bindparams(
                nombre=z["nombre"],
                polygon=json.dumps(z["polygon"], ensure_ascii=False),
                nivel=z["nivel"],
                observacion=z["observacion"],
            )
        )

    op.execute("ALTER TABLE sedimentation_zones ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("sedimentation_zones")
