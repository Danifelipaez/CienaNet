"""alert_log: agrega alert_type (distingue alertas de semáforo de otros tipos).

Revision ID: 013
Revises: 012
Create Date: 2026-08-30

Hasta ahora alert_log solo guardaba alertas de cambio de color de semáforo
(app/services/alert_service.py::maybe_send_alert). Se agrega la alerta de
vendaval (ráfaga de viento pronosticada por encima de un umbral, ver
docs/ALERTAS_VENDAVAL.md) al mismo log de auditoría, pero es un tipo de
alerta distinto — sin esta columna, maybe_send_alert() leería la última fila
sin importar su tipo y compararía un color de vendaval contra un color de
semáforo, rompiendo su dedup. Nullable + default para no romper filas
existentes (todas son 'semaforo').
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_log",
        sa.Column("alert_type", sa.String(20), server_default=sa.text("'semaforo'"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_log", "alert_type")
