"""Script de verificación manual (NO es parte de la suite de pytest): confirma
que el advisory lock en maybe_send_alert() evita envíos duplicados bajo
llamadas concurrentes reales. Requiere una Postgres real y desechable — NUNCA
apuntar esto a la base de datos de producción/Supabase.

Uso:
  1) docker run --rm -d --name cienanet-lock-test -p 5433:5432 \
       -e POSTGRES_PASSWORD=test postgres:16
  2) POSTGRES_URL_NON_POOLING=postgresql://postgres:test@localhost:5433/postgres \
     DATABASE_URL_DIRECT=postgresql://postgres:test@localhost:5433/postgres \
     alembic upgrade head
  3) POSTGRES_PRISMA_URL=postgresql://postgres:test@localhost:5433/postgres \
     POSTGRES_URL_NON_POOLING=postgresql://postgres:test@localhost:5433/postgres \
     python scripts/verify_alert_lock.py
  4) docker stop cienanet-lock-test

Para confirmar que este script SÍ detectaría el bug original: comentar
temporalmente la línea de pg_advisory_xact_lock en alert_service.py y volver a
correr — debería fallar (más de 1 fila en alert_log / más de 1 envío).
"""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.messaging import AlertLog, User
from app.services.alert_service import maybe_send_alert


async def main() -> None:
    async with AsyncSessionLocal() as setup_db:
        setup_db.add(User(wa_id=f"+57{uuid4().hex[:9]}", alertas_activas=True))
        await setup_db.commit()

    semaphore = {"color": "red", "reason": "prueba de concurrencia"}

    with patch(
        "app.services.whatsapp_service.send_template_message",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_send:
        async with AsyncSessionLocal() as db1, AsyncSessionLocal() as db2:
            await asyncio.gather(
                maybe_send_alert(semaphore, db1),
                maybe_send_alert(semaphore, db2),
            )

    async with AsyncSessionLocal() as check_db:
        rows = (await check_db.execute(select(AlertLog))).scalars().all()

    print(f"Filas en alert_log: {len(rows)} (esperado: 1)")
    print(f"Llamadas a send_template_message: {mock_send.await_count} (esperado: 1)")
    assert len(rows) == 1, "BUG: se insertaron múltiples AlertLog — el lock no serializó"
    assert mock_send.await_count == 1, "BUG: se envió la alerta más de una vez"
    print("OK: el advisory lock evitó el envío duplicado.")


if __name__ == "__main__":
    asyncio.run(main())
