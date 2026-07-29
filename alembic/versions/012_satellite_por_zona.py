"""satellite_data: agrega desglose por zona IPP (por_zona).

Revision ID: 012
Revises: 011
Create Date: 2026-07-28

La respuesta griddap de ERDDAP ya trae latitude/longitude por fila — antes se
promediaba todo el bounding box en dos escalares (sst_celsius, chlorophyll_mgm3)
y se tiraba la información espacial ya descargada. `por_zona` guarda el
desglose por las 6 zonas del IPP cuando hay píxel válido cerca del centroide de
cada una (ver app/services/ingestion/satellite.py). Aditivo: las columnas
escalares siguen siendo la media del box, sin cambio de significado.

Nota: junto con esta migración se ajustó el bounding box de ERDDAP a los 3
vértices medidos en campo (docs/KNOWLEDGE_BASE.md §12) — de
(10.5-11.2, -74.85/-73.9) a (10.54-11.01, -74.69/-74.32). Los valores de
sst_celsius/chlorophyll_mgm3 guardados ANTES de esta fecha promedian un área
mayor (incluye Caribe abierto y tierra) y no son directamente comparables con
los de después. `source` se deja igual ("nasa_mur") a propósito: el read
DB-first de dashboard_service.py filtra por ese valor y cambiarlo lo rompería
en silencio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "satellite_data",
        sa.Column("por_zona", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("satellite_data", "por_zona")
