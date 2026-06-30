"""Fishing points: conocimiento territorial comunitario + FK desde catch_reports.

Revision ID: 003
Revises: 002
Create Date: 2026-06-30

Rangos de salinidad (sal_min/sal_max) son estimados a partir de la posición
geográfica de cada punto frente a las 6 zonas IPP ya definidas en
app/services/ipp.py — pendiente de validar con el equipo de análisis
territorial (ver docs/CONTEXT.md, rol "Diego"). Ajustar libremente sin
necesidad de nueva migración: son datos, no esquema.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POINTS = [
    {"nombre": "Boquerón", "lat": 10.982, "lng": -74.402, "sal_min": 20, "sal_max": 36,
     "especies": ["camarón", "lisa"],
     "observacion": "Aguas claras esta semana. Pesca de lisa estable según pescadores de la zona."},
    {"nombre": "Punta Blanca", "lat": 10.921, "lng": -74.471, "sal_min": 15, "sal_max": 30,
     "especies": ["mojarra", "lisa"],
     "observacion": "Brisa norte fuerte por las tardes. Agua un poco turbia, color verde."},
    {"nombre": "Boca del Pájaro", "lat": 10.864, "lng": -74.433, "sal_min": 8, "sal_max": 22,
     "especies": ["camarón"],
     "observacion": "Floración intensa de clorofila. Reporte comunitario de mortandad de peces el martes."},
    {"nombre": "Caño Grande", "lat": 10.794, "lng": -74.398, "sal_min": 2, "sal_max": 12,
     "especies": ["mojarra", "róbalo"],
     "observacion": "Buena entrada de agua dulce del río. Mojarra abundante cerca del manglar."},
    {"nombre": "Los Muertos", "lat": 10.751, "lng": -74.451, "sal_min": 3, "sal_max": 15,
     "especies": ["camarón", "lisa"],
     "observacion": "Sedimento en suspensión tras las lluvias. Captura de camarón a la baja."},
    {"nombre": "La Ahuyama", "lat": 10.833, "lng": -74.512, "sal_min": 5, "sal_max": 18,
     "especies": ["lisa", "mojarra"],
     "observacion": "Condiciones normales. Pescadores reportan cardúmenes de lisa al amanecer."},
    {"nombre": "Tasajera", "lat": 10.972, "lng": -74.434, "sal_min": 3, "sal_max": 15,
     "especies": ["camarón", "lisa", "mojarra"],
     "observacion": "Punto de referencia comunitario. Estación de monitoreo activa, datos confiables."},
    {"nombre": "Punta Gruesa", "lat": 10.886, "lng": -74.361, "sal_min": 20, "sal_max": 36,
     "especies": ["róbalo", "lisa"],
     "observacion": "Viento norte sostenido. Oleaje dificulta faenas pequeñas."},
    {"nombre": "Santa Rosa", "lat": 10.808, "lng": -74.341, "sal_min": 0, "sal_max": 8,
     "especies": ["camarón"],
     "observacion": "Sedimentación crítica en el caño. Acceso reducido para embarcaciones."},
    {"nombre": "Flamenquito", "lat": 10.944, "lng": -74.521, "sal_min": 15, "sal_max": 30,
     "especies": ["mojarra", "lisa", "camarón"],
     "observacion": "Zona de avistamiento de flamencos. Aguas estables y productivas."},
]


def upgrade() -> None:
    op.create_table(
        "fishing_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("sal_min", sa.Float(), nullable=False),
        sa.Column("sal_max", sa.Float(), nullable=False),
        sa.Column("especies", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("observacion", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_foreign_key(
        "fk_catch_reports_fishing_point_id",
        "catch_reports",
        "fishing_points",
        ["fishing_point_id"],
        ["id"],
    )

    fishing_points_table = sa.table(
        "fishing_points",
        sa.column("nombre", sa.String),
        sa.column("lat", sa.Float),
        sa.column("lng", sa.Float),
        sa.column("sal_min", sa.Float),
        sa.column("sal_max", sa.Float),
        sa.column("especies", postgresql.JSONB),
        sa.column("observacion", sa.Text),
    )
    op.bulk_insert(fishing_points_table, _POINTS)


def downgrade() -> None:
    op.drop_constraint("fk_catch_reports_fishing_point_id", "catch_reports", type_="foreignkey")
    op.drop_table("fishing_points")
