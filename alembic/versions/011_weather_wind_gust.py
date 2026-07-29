"""weather_snapshots: agrega ráfaga de viento (wind_gust_kmh).

Revision ID: 011
Revises: 010
Create Date: 2026-07-28

Open-Meteo sí entrega `wind_gusts_10m` (a diferencia de wttr.in, la fuente del
prototipo original) — ver app/services/ingestion/weather.py y el `# ponytail:`
que quita el `wind_kmh * 1.4` estimado de app/services/semaphore.py.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "weather_snapshots",
        sa.Column("wind_gust_kmh", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("weather_snapshots", "wind_gust_kmh")
