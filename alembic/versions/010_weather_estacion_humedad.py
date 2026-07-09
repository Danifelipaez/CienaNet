"""weather_snapshots: agrega estacion (Tasajera/CGSM) y humedad relativa.

Revision ID: 010
Revises: 009
Create Date: 2026-07-08

Ver app/services/ingestion/weather.py: ahora se consulta Open-Meteo para dos
ubicaciones (Tasajera y el centroide CGSM), no solo una. `estacion` distingue
las filas por ubicación; las filas existentes quedan como 'CGSM' (comportamiento
previo, una sola ubicación). `humidity_pct` es nueva (humedad relativa 2m).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weather_snapshots",
        sa.Column("estacion", sa.String(50), server_default=sa.text("'CGSM'"), nullable=False),
    )
    op.add_column(
        "weather_snapshots",
        sa.Column("humidity_pct", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("weather_snapshots", "humidity_pct")
    op.drop_column("weather_snapshots", "estacion")
