"""Envía un aviso manual real a todos los pescadores suscritos (alertas_activas=True).

Para eventos confirmados por una fuente externa sin ingesta automática (boletín
IDEAM de onda tropical, aviso DIMAR/CIOH, etc.) — ver alert_service.py::send_manual_alert.

Pide confirmación explícita porque manda WhatsApp real a toda la base de
suscritos: NUNCA correr esto sin revisar el mensaje y el conteo de
destinatarios que imprime antes de confirmar.

Uso:
  python scripts/send_manual_alert.py "texto del aviso" [--yes]

--yes salta la confirmación interactiva (uso en cron/CI, no recomendado a mano).
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.messaging import User
from app.services.alert_service import send_manual_alert


async def main(mensaje: str, skip_confirm: bool) -> None:
    async with AsyncSessionLocal() as db:
        count = (
            await db.execute(select(User).where(User.alertas_activas.is_(True)))
        ).scalars().all()
        print(f"Destinatarios (alertas_activas=True): {len(count)}")
        print(f"Mensaje:\n{mensaje}\n")

        if not skip_confirm:
            resp = input("¿Confirmas el envío real a todos? Escribe 'si' para continuar: ")
            if resp.strip().lower() != "si":
                print("Cancelado — no se envió nada.")
                return

        sent = await send_manual_alert(mensaje, db, alert_type="ideam_onda_tropical")
        print(f"Enviado a {sent} destinatarios.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], skip_confirm="--yes" in sys.argv))
